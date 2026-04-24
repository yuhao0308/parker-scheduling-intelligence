from __future__ import annotations

import asyncio
import calendar as _calendar
from datetime import date, datetime, timezone
from typing import List

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.db import session as db_session
from app.db.session import get_db
from app.models.notification import (
    NotificationKind,
    NotificationStatus,
    SimulatedNotification,
)
from app.models.recommendation import RecommendationLog
from app.models.schedule import Callout, CalloutStatus
from app.models.unit import Unit
from app.schemas.callout import (
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

# Hold strong references to fire-and-forget background tasks so the GC
# can't collect them mid-flight (asyncio docs explicitly warn about this).
_background_jobs: set[asyncio.Task] = set()


async def _run_recommendation_job(
    callout_id: int,
    request: CalloutRequest,
    job_settings: Settings,
) -> None:
    """Run the recommendation pipeline in its own session.

    Spawned via ``asyncio.create_task`` from POST /callouts so the request
    handler can return immediately. Persists the candidates via the existing
    RecommendationLog row that ``generate_recommendations`` writes, and
    flips the Callout's ``status`` field to COMPLETED or FAILED.
    """
    async with db_session.async_session_factory() as db:
        try:
            await generate_recommendations(
                callout=request,
                callout_id=callout_id,
                db=db,
                settings=job_settings,
            )
            callout = await db.get(Callout, callout_id)
            if callout is not None:
                callout.status = CalloutStatus.COMPLETED
                callout.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("recommendation_job_complete", callout_id=callout_id)
        except Exception as exc:  # noqa: BLE001 — record any pipeline failure
            await db.rollback()
            logger.exception(
                "recommendation_job_failed",
                callout_id=callout_id,
                error=str(exc),
            )
            # Use a fresh session — the rolled-back one may be in a bad state.
            async with db_session.async_session_factory() as fail_db:
                callout = await fail_db.get(Callout, callout_id)
                if callout is not None:
                    callout.status = CalloutStatus.FAILED
                    callout.completed_at = datetime.now(timezone.utc)
                    callout.error_message = str(exc) or exc.__class__.__name__
                    await fail_db.commit()


async def _build_job_response(
    callout: Callout, db: AsyncSession
) -> CalloutJobResponse:
    """Assemble the resumable view of a callout from the persisted state."""
    unit = await db.get(Unit, callout.unit_id)
    unit_name = unit.name if unit else callout.unit_id
    called_out = await load_called_out_employee(callout.employee_id, db)

    base = CalloutJobResponse(
        callout_id=callout.id,
        status=CalloutJobStatus(callout.status.value),
        unit_id=callout.unit_id,
        unit_name=unit_name,
        shift_date=callout.shift_date,
        shift_label=callout.shift_label,
        called_out_employee=called_out,
        reported_at=callout.reported_at,
        error_message=callout.error_message,
    )

    if callout.status != CalloutStatus.COMPLETED:
        return base

    # Latest recommendation log for this callout — the pipeline writes one
    # per run; ordering by id desc covers any future retry semantics.
    rec_log = (
        await db.execute(
            select(RecommendationLog)
            .where(RecommendationLog.callout_id == callout.id)
            .order_by(RecommendationLog.id.desc())
        )
    ).scalars().first()

    if rec_log is None:
        # Status says completed but no log — surface as failure to avoid a
        # stuck spinner on the client.
        base.status = CalloutJobStatus.FAILED
        base.error_message = "Recommendation result missing"
        return base

    candidates = [ScoredCandidate.model_validate(c) for c in rec_log.ranked_candidates]
    filter_stats = FilterStats.model_validate(rec_log.filter_stats)

    return base.model_copy(
        update={
            "recommendation_log_id": rec_log.id,
            "candidates": candidates,
            "filter_stats": filter_stats,
            "generated_at": rec_log.request_timestamp,
        }
    )


@router.post(
    "/callouts",
    response_model=CalloutJobResponse,
    summary="Report a callout and start the recommendation pipeline",
    description=(
        "Creates a callout record, kicks off the recommendation pipeline as "
        "a background task, and returns the job descriptor immediately. "
        "Poll GET /callouts/{callout_id} for status and final candidates."
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
    await db.commit()
    await db.refresh(callout)

    # Fire-and-forget — the task opens its own session and updates the row.
    task = asyncio.create_task(
        _run_recommendation_job(callout.id, request, settings)
    )
    _background_jobs.add(task)
    task.add_done_callback(_background_jobs.discard)

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


@router.get(
    "/callouts/{callout_id}",
    response_model=CalloutJobResponse,
    summary="Fetch the current status and (if ready) candidates for a callout",
)
async def get_callout(
    callout_id: int,
    db: AsyncSession = Depends(get_db),
) -> CalloutJobResponse:
    callout = await db.get(Callout, callout_id)
    if callout is None:
        raise HTTPException(status_code=404, detail="Callout not found")
    return await _build_job_response(callout, db)


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
