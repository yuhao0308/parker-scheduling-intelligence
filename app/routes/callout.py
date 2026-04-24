from __future__ import annotations

import asyncio
import calendar as _calendar
from datetime import date, datetime, timezone
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.db import session as db_session
from app.db.session import get_db
from app.exceptions import AppError
from app.models.notification import (
    NotificationKind,
    NotificationStatus,
    SimulatedNotification,
)
from app.models.recommendation import RecommendationLog
from app.models.schedule import Callout, CalloutStatus
from app.models.staff import StaffMaster
from app.models.unit import Unit
from app.schemas.callout import (
    CalledOutEmployee,
    CalloutDayCount,
    CalloutJobResponse,
    CalloutJobStatus,
    CalloutRequest,
)
from app.schemas.candidate import FilterStats, ScoredCandidate
from app.schemas.outreach import (
    OutreachNotificationOut,
    RespondOutreachRequest,
    RespondOutreachResult,
    SendOutreachRequest,
    SendOutreachResult,
)
from app.services.outreach import respond_to_outreach, send_outreach
from app.services.recommendation import (
    generate_recommendations,
    load_called_out_employee,
)

logger = structlog.get_logger()

router = APIRouter(tags=["callout"])

DEMO_COORDINATOR_ID = "demo-scheduler"

# Keep strong references to fire-and-forget background tasks so the GC
# doesn't reap them mid-flight. Tasks remove themselves on completion.
_background_jobs: set[asyncio.Task] = set()


@router.post(
    "/callouts",
    response_model=CalloutJobResponse,
    summary="Report a callout and kick off replacement recommendations",
    description=(
        "Persists the callout, spawns the recommendation pipeline as an "
        "asyncio background task, and returns immediately with "
        "status=RUNNING. Poll GET /callouts/{id} until COMPLETED/FAILED."
    ),
)
async def create_callout(
    request: CalloutRequest,
    db: AsyncSession = Depends(get_db),
) -> CalloutJobResponse:
    callout = Callout(
        employee_id=request.callout_employee_id,
        unit_id=request.unit_id,
        shift_date=request.shift_date,
        shift_label=request.shift_label,
        reported_at=datetime.now(timezone.utc),
        status=CalloutStatus.RUNNING,
    )
    db.add(callout)
    await db.flush()
    callout_id = callout.id
    await db.commit()
    await db.refresh(callout)

    # Spawn the recommendation pipeline. The task opens its own DB
    # session so it survives the request scope closing.
    task = asyncio.create_task(
        _run_recommendation_job(callout_id=callout_id, request=request, app_settings=settings)
    )
    _background_jobs.add(task)
    task.add_done_callback(_background_jobs.discard)

    return await _build_job_response(callout, db)


@router.get(
    "/callouts/{callout_id}",
    response_model=CalloutJobResponse,
    summary="Fetch the current status of a callout recommendation job",
)
async def get_callout_job(
    callout_id: int,
    db: AsyncSession = Depends(get_db),
) -> CalloutJobResponse:
    callout = await db.get(Callout, callout_id)
    if callout is None:
        raise HTTPException(status_code=404, detail=f"Callout {callout_id} not found")
    return await _build_job_response(callout, db)


@router.get(
    "/callouts",
    response_model=List[CalloutDayCount],
    summary="Per-date callout rollup for the given month",
    description=(
        "Feeds the main calendar's day-level red indicators and the Callout "
        "tab's mini-calendar. A callout is 'active' until an outreach attempt "
        "for it lands in ACCEPTED state."
    ),
)
async def list_callouts_by_month(
    month: str = Query(..., description="YYYY-MM"),
    db: AsyncSession = Depends(get_db),
) -> List[CalloutDayCount]:
    try:
        year_str, month_str = month.split("-")
        year, month_num = int(year_str), int(month_str)
    except (ValueError, AttributeError):
        return []
    _, last_day = _calendar.monthrange(year, month_num)
    first = date(year, month_num, 1)
    last = date(year, month_num, last_day)

    callouts = list(
        (
            await db.execute(
                select(Callout).where(Callout.shift_date.between(first, last))
            )
        )
        .scalars()
        .all()
    )
    if not callouts:
        return []

    # Callouts that have any ACCEPTED outreach notification are considered resolved.
    resolved_q = (
        select(SimulatedNotification.callout_id)
        .where(
            SimulatedNotification.callout_id.in_([c.id for c in callouts]),
            SimulatedNotification.kind == NotificationKind.CALLOUT_OUTREACH,
            SimulatedNotification.status == NotificationStatus.ACCEPTED,
        )
        .distinct()
    )
    resolved_ids = {row[0] for row in (await db.execute(resolved_q)).all()}

    rollup: dict[date, tuple[int, int]] = {}
    for c in callouts:
        total, active = rollup.get(c.shift_date, (0, 0))
        total += 1
        if c.id not in resolved_ids:
            active += 1
        rollup[c.shift_date] = (total, active)

    return [
        CalloutDayCount(date=d, total=t, active=a)
        for d, (t, a) in sorted(rollup.items())
    ]


@router.post(
    "/callouts/{callout_id}/outreach/next",
    response_model=SendOutreachResult,
    summary="Simulate SMS/email outreach to the next ranked candidate",
)
async def send_outreach_next(
    callout_id: int,
    req: SendOutreachRequest,
    db: AsyncSession = Depends(get_db),
) -> SendOutreachResult:
    return await send_outreach(
        db=db,
        callout_id=callout_id,
        recommendation_log_id=req.recommendation_log_id,
        candidate_employee_id=req.candidate_employee_id,
        rank=req.rank,
    )


@router.post(
    "/callouts/{callout_id}/outreach/{notification_id}/respond",
    response_model=RespondOutreachResult,
    summary="Record Accept/Decline/Timeout/Skip for an outreach attempt",
)
async def respond_outreach(
    callout_id: int,
    notification_id: int,
    req: RespondOutreachRequest,
    db: AsyncSession = Depends(get_db),
) -> RespondOutreachResult:
    return await respond_to_outreach(
        db=db,
        callout_id=callout_id,
        notification_id=notification_id,
        response=req.response,
        rank=req.rank,
        override_reason=req.override_reason,
        coordinator_id=DEMO_COORDINATOR_ID,
    )


@router.get(
    "/callouts/{callout_id}/outreach",
    response_model=List[OutreachNotificationOut],
    summary="List outreach attempts for a given callout (for the UI console)",
)
async def list_outreach(
    callout_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[OutreachNotificationOut]:
    q = (
        select(SimulatedNotification)
        .where(
            SimulatedNotification.callout_id == callout_id,
            SimulatedNotification.kind == NotificationKind.CALLOUT_OUTREACH,
        )
        .order_by(SimulatedNotification.created_at.asc())
    )
    notifications = list((await db.execute(q)).scalars().all())
    return [
        OutreachNotificationOut(
            notification_id=n.id,
            employee_id=n.employee_id,
            status=n.status.value,
            created_at=n.created_at,
            responded_at=n.responded_at,
            payload_text=n.payload_text,
        )
        for n in notifications
    ]


# --- helpers ---------------------------------------------------------------


async def _build_job_response(
    callout: Callout, db: AsyncSession
) -> CalloutJobResponse:
    """Hydrate a CalloutJobResponse from a persisted Callout row.

    When status=COMPLETED, loads the latest RecommendationLog for this
    callout and inlines candidates + filter_stats. If COMPLETED but no
    log exists, surfaces the condition as FAILED so the UI doesn't hang.
    """

    unit = await db.get(Unit, callout.unit_id)
    unit_name = unit.name if unit else callout.unit_id

    called_out: Optional[CalledOutEmployee] = None
    try:
        called_out = await load_called_out_employee(callout.employee_id, db)
    except Exception:  # pragma: no cover — defensive
        called_out = None

    status = CalloutJobStatus(callout.status.value)
    error_message = callout.error_message
    candidates: Optional[List[ScoredCandidate]] = None
    filter_stats: Optional[FilterStats] = None
    generated_at: Optional[datetime] = None
    recommendation_log_id: Optional[int] = None

    if status == CalloutJobStatus.COMPLETED:
        rec = (
            await db.execute(
                select(RecommendationLog)
                .where(RecommendationLog.callout_id == callout.id)
                .order_by(RecommendationLog.id.desc())
            )
        ).scalars().first()
        if rec is None:
            status = CalloutJobStatus.FAILED
            if not error_message:
                error_message = "Recommendation result missing"
        else:
            recommendation_log_id = rec.id
            candidates = [
                ScoredCandidate.model_validate(c) for c in (rec.ranked_candidates or [])
            ]
            filter_stats = FilterStats.model_validate(rec.filter_stats or {})
            generated_at = rec.request_timestamp

    return CalloutJobResponse(
        callout_id=callout.id,
        status=status,
        unit_id=callout.unit_id,
        unit_name=unit_name,
        shift_date=callout.shift_date,
        shift_label=callout.shift_label,
        called_out_employee=called_out,
        reported_at=callout.reported_at,
        error_message=error_message,
        recommendation_log_id=recommendation_log_id,
        candidates=candidates,
        filter_stats=filter_stats,
        generated_at=generated_at,
    )


async def _run_recommendation_job(
    callout_id: int,
    request: CalloutRequest,
    app_settings: Settings,
) -> None:
    """Background worker: run the pipeline in a dedicated session.

    Late-binds db_session.async_session_factory so tests that patch the
    module attribute with a SQLite sessionmaker get picked up here.
    """

    session_factory = db_session.async_session_factory
    try:
        async with session_factory() as session:
            try:
                await generate_recommendations(
                    callout=request,
                    callout_id=callout_id,
                    db=session,
                    settings=app_settings,
                )
                callout = await session.get(Callout, callout_id)
                if callout is not None:
                    callout.status = CalloutStatus.COMPLETED
                    callout.completed_at = datetime.now(timezone.utc)
                    callout.error_message = None
                await session.commit()
                return
            except Exception as exc:
                await session.rollback()
                raise
    except Exception as exc:  # noqa: BLE001 — we want to serialize any failure
        logger.exception("callout_job_failed", callout_id=callout_id)
        message = str(exc) or exc.__class__.__name__
        # Open a fresh session — the previous one may be in a bad state
        # after the rollback.
        try:
            async with session_factory() as session:
                callout = await session.get(Callout, callout_id)
                if callout is not None:
                    callout.status = CalloutStatus.FAILED
                    callout.completed_at = datetime.now(timezone.utc)
                    callout.error_message = message[:2000]
                    await session.commit()
        except Exception:  # pragma: no cover — last-resort
            logger.exception("callout_job_failure_persist_failed", callout_id=callout_id)
