from __future__ import annotations

import calendar as _calendar
from datetime import date, datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.db.session import get_db
from app.models.notification import (
    NotificationKind,
    NotificationStatus,
    SimulatedNotification,
)
from app.models.schedule import Callout
from app.models.staff import StaffMaster
from app.schemas.callout import CalloutDayCount, CalloutRequest, CalloutResponse
from app.schemas.outreach import (
    OutreachNotificationOut,
    RespondOutreachRequest,
    RespondOutreachResult,
    SendOutreachRequest,
    SendOutreachResult,
)
from app.services.outreach import respond_to_outreach, send_outreach
from app.services.recommendation import generate_recommendations

router = APIRouter(tags=["callout"])

DEMO_COORDINATOR_ID = "demo-scheduler"


@router.post(
    "/callouts",
    response_model=CalloutResponse,
    summary="Report a callout and rank replacement candidates",
    description=(
        "Creates a callout record, runs the recommendation pipeline, and returns "
        "ranked candidates with scoring details and filter statistics."
    ),
)
async def create_callout(
    request: CalloutRequest,
    db: AsyncSession = Depends(get_db),
) -> CalloutResponse:
    """Report a call-out and get ranked replacement candidates."""
    # Create the callout record
    callout = Callout(
        employee_id=request.callout_employee_id,
        unit_id=request.unit_id,
        shift_date=request.shift_date,
        shift_label=request.shift_label,
        reported_at=datetime.now(timezone.utc),
    )
    db.add(callout)
    await db.flush()  # get the callout ID

    # Run the recommendation pipeline
    response = await generate_recommendations(
        callout=request,
        callout_id=callout.id,
        db=db,
        settings=settings,
    )

    await db.commit()
    return response


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
