"""Confirmation flow service: send, list, respond, replace.

Backs the scheduler-side "without nurse login" demo flow. Nurse replies
are simulated by the scheduler clicking Accept/Decline on the console;
the real SMS/email integration is out of scope.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.exceptions import AppError
from app.models.notification import (
    NotificationChannel,
    NotificationKind,
    NotificationStatus,
    SimulatedNotification,
)
from app.models.recommendation import OverrideLog
from app.models.schedule import Callout, ConfirmationStatus, ScheduleEntry
from app.models.staff import StaffMaster
from app.models.unit import Unit
from app.schemas.callout import CalloutRequest, CalloutResponse
from app.schemas.common import ShiftLabel
from app.schemas.confirmation import (
    ConfirmationEntryOut,
    ConfirmationListOut,
    ConfirmationResponse,
    RemoveEntryResult,
    ReplaceEntryResult,
    RespondConfirmationResult,
    SendConfirmationsResult,
    StatusCounts,
)
from app.services.recommendation import generate_recommendations


def _week_range(week_start: date) -> tuple[date, date]:
    return week_start, week_start + timedelta(days=6)


async def send_week_confirmations(
    db: AsyncSession,
    week_start: date,
    unit_ids: Optional[List[str]],
) -> SendConfirmationsResult:
    """Flip UNSENT entries to PENDING and create simulated notifications."""
    start, end = _week_range(week_start)

    query = select(ScheduleEntry).where(
        and_(
            ScheduleEntry.shift_date >= start,
            ScheduleEntry.shift_date <= end,
            ScheduleEntry.confirmation_status == ConfirmationStatus.UNSENT,
        )
    )
    if unit_ids:
        query = query.where(ScheduleEntry.unit_id.in_(unit_ids))

    result = await db.execute(query)
    entries = list(result.scalars().all())

    now = datetime.now(timezone.utc)
    for entry in entries:
        entry.confirmation_status = ConfirmationStatus.PENDING
        entry.confirmation_sent_at = now
        db.add(
            SimulatedNotification(
                schedule_entry_id=entry.id,
                employee_id=entry.employee_id,
                channel=NotificationChannel.SMS,
                kind=NotificationKind.CONFIRM_SHIFT,
                status=NotificationStatus.SENT,
                payload_text=(
                    f"Please confirm your {entry.shift_label.value} shift on "
                    f"{entry.shift_date.isoformat()} at {entry.unit_id}."
                ),
                created_at=now,
            )
        )

    await db.flush()

    counts = await _status_counts(db, start, end, unit_ids)
    await db.commit()
    return SendConfirmationsResult(
        week_start=week_start,
        entries_marked=len(entries),
        notifications_created=len(entries),
        counts_by_status=counts,
    )


async def list_week_confirmations(
    db: AsyncSession,
    week_start: date,
    unit_ids: Optional[List[str]],
) -> ConfirmationListOut:
    start, end = _week_range(week_start)

    entries_q = select(ScheduleEntry).where(
        and_(
            ScheduleEntry.shift_date >= start,
            ScheduleEntry.shift_date <= end,
            ScheduleEntry.confirmation_status != ConfirmationStatus.UNSENT,
        )
    )
    if unit_ids:
        entries_q = entries_q.where(ScheduleEntry.unit_id.in_(unit_ids))

    entries = list((await db.execute(entries_q)).scalars().all())

    if not entries:
        return ConfirmationListOut(
            week_start=week_start, entries=[], summary=StatusCounts()
        )

    staff_ids = {e.employee_id for e in entries}
    staff = {
        s.employee_id: s
        for s in (
            await db.execute(
                select(StaffMaster).where(StaffMaster.employee_id.in_(staff_ids))
            )
        ).scalars()
    }

    unit_ids_all = {e.unit_id for e in entries}
    units = {
        u.unit_id: u
        for u in (
            await db.execute(select(Unit).where(Unit.unit_id.in_(unit_ids_all)))
        ).scalars()
    }

    latest_notif: dict[int, int] = {}
    notif_q = (
        select(SimulatedNotification.id, SimulatedNotification.schedule_entry_id)
        .where(
            SimulatedNotification.schedule_entry_id.in_([e.id for e in entries]),
            SimulatedNotification.kind == NotificationKind.CONFIRM_SHIFT,
        )
        .order_by(SimulatedNotification.created_at.desc())
    )
    for nid, eid in (await db.execute(notif_q)).all():
        if eid not in latest_notif:
            latest_notif[eid] = nid

    out_entries = []
    for e in entries:
        s = staff.get(e.employee_id)
        u = units.get(e.unit_id)
        out_entries.append(
            ConfirmationEntryOut(
                entry_id=e.id,
                employee_id=e.employee_id,
                name=s.name if s else e.employee_id,
                license=s.license.value if s else "UNK",
                unit_id=e.unit_id,
                unit_name=u.name if u else e.unit_id,
                shift_date=e.shift_date,
                shift_label=e.shift_label.value,
                confirmation_status=e.confirmation_status.value,
                confirmation_sent_at=e.confirmation_sent_at,
                confirmation_responded_at=e.confirmation_responded_at,
                latest_notification_id=latest_notif.get(e.id),
            )
        )

    out_entries.sort(key=lambda x: (x.shift_date, x.unit_id, x.shift_label))
    summary = await _status_counts(db, start, end, unit_ids)
    return ConfirmationListOut(week_start=week_start, entries=out_entries, summary=summary)


async def respond_to_confirmation(
    db: AsyncSession,
    entry_id: int,
    response: ConfirmationResponse,
    settings: Settings,
) -> RespondConfirmationResult:
    entry = await db.get(ScheduleEntry, entry_id)
    if not entry:
        raise AppError(f"ScheduleEntry {entry_id} not found", status_code=404)
    if entry.confirmation_status != ConfirmationStatus.PENDING:
        raise AppError(
            f"Entry {entry_id} is not PENDING (current: {entry.confirmation_status.value})",
            status_code=409,
        )

    now = datetime.now(timezone.utc)
    await _mark_latest_notification(
        db,
        entry_id,
        NotificationKind.CONFIRM_SHIFT,
        status=_notification_status_for(response),
        responded_at=now,
    )

    if response == ConfirmationResponse.ACCEPTED:
        entry.confirmation_status = ConfirmationStatus.ACCEPTED
        entry.confirmation_responded_at = now
        await db.commit()
        return RespondConfirmationResult(
            entry_id=entry_id, new_status=entry.confirmation_status.value
        )

    # DECLINED or TIMEOUT → mark declined + run recommendations for this slot.
    entry.confirmation_status = ConfirmationStatus.DECLINED
    entry.confirmation_responded_at = now

    callout = Callout(
        employee_id=entry.employee_id,
        unit_id=entry.unit_id,
        shift_date=entry.shift_date,
        shift_label=entry.shift_label,
        reason=f"schedule_decline:{response.value.lower()}",
        reported_at=now,
    )
    db.add(callout)
    await db.flush()

    rec_request = CalloutRequest(
        callout_employee_id=entry.employee_id,
        unit_id=entry.unit_id,
        shift_date=entry.shift_date,
        shift_label=ShiftLabel(entry.shift_label.value),
    )
    replacement = await generate_recommendations(
        callout=rec_request,
        callout_id=callout.id,
        db=db,
        settings=settings,
    )

    await db.commit()
    return RespondConfirmationResult(
        entry_id=entry_id,
        new_status=entry.confirmation_status.value,
        replacement=replacement,
    )


async def replace_declined_entry(
    db: AsyncSession,
    entry_id: int,
    recommendation_log_id: int,
    selected_employee_id: str,
    selected_rank: Optional[int],
    coordinator_id: str,
) -> ReplaceEntryResult:
    old_entry = await db.get(ScheduleEntry, entry_id)
    if not old_entry:
        raise AppError(f"ScheduleEntry {entry_id} not found", status_code=404)
    if old_entry.confirmation_status != ConfirmationStatus.DECLINED:
        raise AppError(
            f"Entry {entry_id} must be DECLINED to replace "
            f"(current: {old_entry.confirmation_status.value})",
            status_code=409,
        )

    now = datetime.now(timezone.utc)
    new_entry = ScheduleEntry(
        employee_id=selected_employee_id,
        unit_id=old_entry.unit_id,
        shift_date=old_entry.shift_date,
        shift_label=old_entry.shift_label,
        is_published=True,
        confirmation_status=ConfirmationStatus.PENDING,
        confirmation_sent_at=now,
    )
    db.add(new_entry)
    await db.flush()

    old_entry.confirmation_status = ConfirmationStatus.REPLACED
    old_entry.replaced_by_entry_id = new_entry.id

    db.add(
        OverrideLog(
            recommendation_log_id=recommendation_log_id,
            selected_employee_id=selected_employee_id,
            selected_rank=selected_rank,
            override_reason="decline_replacement",
            feedback_tag=None,
            coordinator_id=coordinator_id,
            timestamp=now,
        )
    )

    db.add(
        SimulatedNotification(
            schedule_entry_id=new_entry.id,
            recommendation_log_id=recommendation_log_id,
            employee_id=selected_employee_id,
            channel=NotificationChannel.SMS,
            kind=NotificationKind.CONFIRM_SHIFT,
            status=NotificationStatus.SENT,
            payload_text=(
                f"You have been assigned to cover a declined {new_entry.shift_label.value} "
                f"shift on {new_entry.shift_date.isoformat()} at {new_entry.unit_id}. "
                "Please confirm."
            ),
            created_at=now,
        )
    )

    await db.commit()
    return ReplaceEntryResult(
        old_entry_id=entry_id,
        new_entry_id=new_entry.id,
        new_status=ConfirmationStatus.PENDING.value,
    )


async def remove_entry(
    db: AsyncSession,
    entry_id: int,
) -> RemoveEntryResult:
    """Manually drop a nurse from a slot (the supervisor's 'Remove from pool').

    Marks the entry REPLACED with replaced_by_entry_id=NULL to signal the
    slot is now open, cancels the outstanding CONFIRM_SHIFT notification
    if one is pending, and lets the scheduler re-run Auto-Gen to refill.
    Accepts entries in any state except already-REPLACED.
    """
    entry = await db.get(ScheduleEntry, entry_id)
    if not entry:
        raise AppError(f"ScheduleEntry {entry_id} not found", status_code=404)
    if entry.confirmation_status == ConfirmationStatus.REPLACED:
        raise AppError(
            f"Entry {entry_id} is already REPLACED", status_code=409
        )

    now = datetime.now(timezone.utc)

    # Cancel any still-open notification for this entry.
    canceled_notif_id: Optional[int] = None
    notif_q = (
        select(SimulatedNotification)
        .where(
            SimulatedNotification.schedule_entry_id == entry_id,
            SimulatedNotification.kind == NotificationKind.CONFIRM_SHIFT,
            SimulatedNotification.status == NotificationStatus.SENT,
        )
        .order_by(SimulatedNotification.created_at.desc())
    )
    latest = (await db.execute(notif_q)).scalars().first()
    if latest:
        latest.status = NotificationStatus.CANCELED
        latest.responded_at = now
        canceled_notif_id = latest.id

    entry.confirmation_status = ConfirmationStatus.REPLACED
    entry.replaced_by_entry_id = None  # sentinel: slot now open
    entry.confirmation_responded_at = now

    await db.commit()
    return RemoveEntryResult(
        entry_id=entry_id,
        new_status=ConfirmationStatus.REPLACED.value,
        slot_now_open=True,
        canceled_notification_id=canceled_notif_id,
    )


async def _status_counts(
    db: AsyncSession,
    start: date,
    end: date,
    unit_ids: Optional[List[str]],
) -> StatusCounts:
    q = select(ScheduleEntry.confirmation_status, ScheduleEntry.id).where(
        and_(ScheduleEntry.shift_date >= start, ScheduleEntry.shift_date <= end)
    )
    if unit_ids:
        q = q.where(ScheduleEntry.unit_id.in_(unit_ids))

    counts = StatusCounts()
    for status, _id in (await db.execute(q)).all():
        key = status.value.lower() if hasattr(status, "value") else str(status).lower()
        if hasattr(counts, key):
            setattr(counts, key, getattr(counts, key) + 1)
    return counts


def _notification_status_for(response: ConfirmationResponse) -> NotificationStatus:
    if response == ConfirmationResponse.ACCEPTED:
        return NotificationStatus.ACCEPTED
    if response == ConfirmationResponse.TIMEOUT:
        return NotificationStatus.TIMEOUT
    return NotificationStatus.DECLINED


async def _mark_latest_notification(
    db: AsyncSession,
    entry_id: int,
    kind: NotificationKind,
    status: NotificationStatus,
    responded_at: datetime,
) -> None:
    q = (
        select(SimulatedNotification)
        .where(
            SimulatedNotification.schedule_entry_id == entry_id,
            SimulatedNotification.kind == kind,
            SimulatedNotification.status == NotificationStatus.SENT,
        )
        .order_by(SimulatedNotification.created_at.desc())
    )
    latest = (await db.execute(q)).scalars().first()
    if latest:
        latest.status = status
        latest.responded_at = responded_at
