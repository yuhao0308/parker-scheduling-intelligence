"""Last-minute callout outreach service.

Represents one-at-a-time ranked outreach: scheduler sends to candidate #1,
sees yes/no/timeout, then picks next. On accept we create the replacement
ScheduleEntry and cancel sibling outreach rows for that callout.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.models.notification import (
    NotificationChannel,
    NotificationKind,
    NotificationStatus,
    SimulatedNotification,
)
from app.models.recommendation import OverrideLog, RecommendationLog
from app.models.schedule import Callout, ConfirmationStatus, ScheduleEntry
from app.schemas.outreach import (
    OutreachResponse,
    RespondOutreachResult,
    SendOutreachResult,
)


async def send_outreach(
    db: AsyncSession,
    callout_id: int,
    recommendation_log_id: int,
    candidate_employee_id: str,
    rank: int | None,
) -> SendOutreachResult:
    callout = await db.get(Callout, callout_id)
    if not callout:
        raise AppError(f"Callout {callout_id} not found", status_code=404)

    now = datetime.now(timezone.utc)
    notification = SimulatedNotification(
        callout_id=callout_id,
        recommendation_log_id=recommendation_log_id,
        employee_id=candidate_employee_id,
        channel=NotificationChannel.SMS,
        kind=NotificationKind.CALLOUT_OUTREACH,
        status=NotificationStatus.SENT,
        payload_text=(
            f"Urgent: can you cover the {callout.shift_label.value} shift on "
            f"{callout.shift_date.isoformat()} at {callout.unit_id}? "
            "Reply YES or NO within 15 minutes."
        ),
        created_at=now,
    )
    db.add(notification)
    await db.flush()

    await db.commit()
    return SendOutreachResult(
        notification_id=notification.id,
        callout_id=callout_id,
        employee_id=candidate_employee_id,
        rank=rank,
        status=notification.status.value,
    )


async def respond_to_outreach(
    db: AsyncSession,
    callout_id: int,
    notification_id: int,
    response: OutreachResponse,
    rank: int | None,
    override_reason: str | None,
    coordinator_id: str,
) -> RespondOutreachResult:
    notification = await db.get(SimulatedNotification, notification_id)
    if not notification:
        raise AppError(f"Notification {notification_id} not found", status_code=404)
    if notification.callout_id != callout_id:
        raise AppError(
            f"Notification {notification_id} does not belong to callout {callout_id}",
            status_code=400,
        )
    if notification.status != NotificationStatus.SENT:
        raise AppError(
            f"Notification already resolved (status={notification.status.value})",
            status_code=409,
        )

    now = datetime.now(timezone.utc)
    notification.responded_at = now
    notification.status = _status_for(response)

    if response != OutreachResponse.ACCEPTED:
        # Move-to-bottom semantics: timeouts and declines don't remove the
        # candidate from consideration — they signal the UI to drop them to
        # the bottom of the ranked list. The cumulative list of deprioritized
        # employees for this callout is computed from all non-accepted
        # outreach attempts so far.
        deprioritized = await _collect_deprioritized(db, callout_id)
        await db.commit()
        return RespondOutreachResult(
            notification_id=notification_id,
            status=notification.status.value,
            deprioritized_employee_ids=deprioritized,
        )

    # ACCEPTED → create the replacement ScheduleEntry, log override, cancel siblings.
    callout = await db.get(Callout, callout_id)
    rec = await db.get(RecommendationLog, notification.recommendation_log_id) if notification.recommendation_log_id else None

    new_entry = ScheduleEntry(
        employee_id=notification.employee_id,
        unit_id=callout.unit_id,
        shift_date=callout.shift_date,
        shift_label=callout.shift_label,
        is_published=True,
        confirmation_status=ConfirmationStatus.PENDING,
        confirmation_sent_at=now,
    )
    db.add(new_entry)
    await db.flush()

    if rec:
        db.add(
            OverrideLog(
                recommendation_log_id=rec.id,
                selected_employee_id=notification.employee_id,
                selected_rank=rank,
                override_reason=override_reason or "callout_outreach_accept",
                feedback_tag=None,
                coordinator_id=coordinator_id,
                timestamp=now,
            )
        )

    canceled_ids = await _cancel_sibling_outreach(
        db, callout_id=callout_id, except_notification_id=notification_id
    )
    deprioritized = await _collect_deprioritized(db, callout_id)

    await db.commit()
    return RespondOutreachResult(
        notification_id=notification_id,
        status=notification.status.value,
        assigned_entry_id=new_entry.id,
        canceled_notification_ids=canceled_ids,
        deprioritized_employee_ids=deprioritized,
    )


# Distinct text emitted on sibling cancellation so the UI can show a
# "we found someone" badge instead of the generic CANCELED state.
FILLED_BY_OTHER_TEXT = (
    "Thank you \u2014 that shift has been filled by another teammate. "
    "No further action needed."
)


async def _cancel_sibling_outreach(
    db: AsyncSession,
    callout_id: int,
    except_notification_id: int,
) -> List[int]:
    q = select(SimulatedNotification).where(
        SimulatedNotification.callout_id == callout_id,
        SimulatedNotification.kind == NotificationKind.CALLOUT_OUTREACH,
        SimulatedNotification.status == NotificationStatus.SENT,
        SimulatedNotification.id != except_notification_id,
    )
    now = datetime.now(timezone.utc)
    canceled = []
    for notif in (await db.execute(q)).scalars():
        notif.status = NotificationStatus.CANCELED
        notif.responded_at = now
        notif.payload_text = FILLED_BY_OTHER_TEXT
        canceled.append(notif.id)
    return canceled


async def _collect_deprioritized(
    db: AsyncSession,
    callout_id: int,
) -> List[str]:
    """Employees whose outreach for this callout ended in TIMEOUT or DECLINED.

    The UI uses this to push them to the bottom of the ranked candidate
    list — not remove them. A single candidate who was contacted twice
    appears once (dedup while preserving first-seen order).
    """
    q = (
        select(SimulatedNotification.employee_id, SimulatedNotification.status)
        .where(
            SimulatedNotification.callout_id == callout_id,
            SimulatedNotification.kind == NotificationKind.CALLOUT_OUTREACH,
            SimulatedNotification.status.in_(
                [NotificationStatus.TIMEOUT, NotificationStatus.DECLINED]
            ),
        )
        .order_by(SimulatedNotification.created_at.asc())
    )
    seen: set[str] = set()
    out: List[str] = []
    for emp_id, _status in (await db.execute(q)).all():
        if emp_id not in seen:
            seen.add(emp_id)
            out.append(emp_id)
    return out


def _status_for(response: OutreachResponse) -> NotificationStatus:
    return {
        OutreachResponse.ACCEPTED: NotificationStatus.ACCEPTED,
        OutreachResponse.DECLINED: NotificationStatus.DECLINED,
        OutreachResponse.TIMEOUT: NotificationStatus.TIMEOUT,
        OutreachResponse.SKIPPED: NotificationStatus.SKIPPED,
    }[response]
