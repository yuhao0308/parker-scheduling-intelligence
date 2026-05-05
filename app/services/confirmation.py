"""Confirmation flow service: send, list, respond, replace.

Backs the scheduler-side "without nurse login" demo flow. Nurse replies
are simulated by the scheduler clicking Accept/Decline on the console;
the real SMS/email integration is out of scope.
"""
from __future__ import annotations

import calendar
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
from app.models.schedule import Callout, CalloutStatus, ConfirmationStatus, ScheduleEntry
from app.models.staff import StaffMaster
from app.models.unit import Unit
from app.schemas.callout import CalloutRequest, CalloutResponse
from app.schemas.common import ShiftLabel
from app.schemas.confirmation import (
    CommitDecision,
    CommitDecisionsResult,
    ConfirmationEntryOut,
    ConfirmationListOut,
    ConfirmationResponse,
    RemoveEntryResult,
    ReplaceEntryResult,
    RespondConfirmationResult,
    SendConfirmationsResult,
    StatusCounts,
    TimeoutSweepResult,
)
from app.services.recommendation import generate_recommendations
from app.services.scheduler import regenerate_month_schedule, regenerate_week_schedule


def _week_range(week_start: date) -> tuple[date, date]:
    return week_start, week_start + timedelta(days=6)


def _month_range(year: int, month: int) -> tuple[date, date]:
    _, last_day = calendar.monthrange(year, month)
    return date(year, month, 1), date(year, month, last_day)


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


async def send_month_confirmations(
    db: AsyncSession,
    year: int,
    month: int,
    unit_ids: Optional[List[str]],
    period_start: Optional[date] = None,
    period_end: Optional[date] = None,
) -> SendConfirmationsResult:
    """Flip UNSENT entries to PENDING and create notifications.

    By default the inclusive range is the calendar month identified by
    ``year``/``month``. When ``period_start`` and ``period_end`` are provided
    they override that range — useful for the 4-week (28-day) rotation flow."""
    if period_start is not None and period_end is not None:
        start, end = period_start, period_end
    else:
        start, end = _month_range(year, month)

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
        week_start=start,
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


async def list_month_confirmations(
    db: AsyncSession,
    year: int,
    month: int,
    unit_ids: Optional[List[str]],
) -> ConfirmationListOut:
    start, end = _month_range(year, month)

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
            week_start=start, entries=[], summary=StatusCounts()
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
    return ConfirmationListOut(week_start=start, entries=out_entries, summary=summary)


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
        status=CalloutStatus.RUNNING,
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

    # The synchronous decline-triggers-recommendation path runs the
    # pipeline inline, so mark it COMPLETED immediately for consistency
    # with the async POST /callouts flow.
    callout.status = CalloutStatus.COMPLETED
    callout.completed_at = datetime.now(timezone.utc)

    await db.commit()
    return RespondConfirmationResult(
        entry_id=entry_id,
        new_status=entry.confirmation_status.value,
        replacement=replacement,
    )


async def commit_week_decisions(
    db: AsyncSession,
    week_start: date,
    decisions: List[CommitDecision],
    employee_pool: List[str],
    settings: Settings,
) -> CommitDecisionsResult:
    """Bulk-commit scheduler review decisions for the Auto-Gen panel.

    Checked entries are ACCEPTED, unchecked entries are DECLINED. Unlike the
    single-entry respond flow, declines here do not synchronously generate
    replacement recommendations; instead, the week is re-rolled once against
    the remaining pool after all decisions are applied.
    """
    start, end = _week_range(week_start)
    decision_map = {decision.entry_id: decision.keep for decision in decisions}

    if not decision_map:
        summary = await _status_counts(db, start, end, unit_ids=None)
        return CommitDecisionsResult(
            week_start=week_start,
            accepted_count=0,
            declined_count=0,
            skipped_count=0,
            declined_employee_ids=[],
            summary=summary,
        )

    query = select(ScheduleEntry).where(
        and_(
            ScheduleEntry.id.in_(decision_map.keys()),
            ScheduleEntry.shift_date >= start,
            ScheduleEntry.shift_date <= end,
        )
    )
    entries = list((await db.execute(query)).scalars().all())

    accepted_count = 0
    declined_count = 0
    skipped_count = max(0, len(decision_map) - len(entries))
    declined_employee_ids: set[str] = set()
    now = datetime.now(timezone.utc)

    for entry in entries:
        if entry.confirmation_status != ConfirmationStatus.PENDING:
            skipped_count += 1
            continue

        keep = decision_map.get(entry.id, True)
        await _mark_latest_notification(
            db,
            entry.id,
            NotificationKind.CONFIRM_SHIFT,
            status=NotificationStatus.ACCEPTED if keep else NotificationStatus.DECLINED,
            responded_at=now,
        )

        entry.confirmation_status = (
            ConfirmationStatus.ACCEPTED if keep else ConfirmationStatus.DECLINED
        )
        entry.confirmation_responded_at = now

        if keep:
            accepted_count += 1
        else:
            declined_count += 1
            declined_employee_ids.add(entry.employee_id)

    reroll_entries_generated = 0
    reroll_notifications_sent = 0
    unfilled_slots = 0
    warnings: list[str] = []

    if declined_employee_ids:
        await db.flush()
        reroll_pool = [
            employee_id
            for employee_id in employee_pool
            if employee_id not in declined_employee_ids
        ]
        if reroll_pool:
            regen = await regenerate_week_schedule(
                week_start=week_start,
                employee_pool=reroll_pool,
                db=db,
                settings=settings,
                preserve_responded=True,
            )
            sent = await send_week_confirmations(db, week_start, unit_ids=None)
            reroll_entries_generated = regen.entries_created
            reroll_notifications_sent = sent.notifications_created
            unfilled_slots = regen.unfilled_slots
            warnings = regen.warnings
        else:
            await db.commit()
    else:
        await db.commit()

    summary = await _status_counts(db, start, end, unit_ids=None)
    return CommitDecisionsResult(
        week_start=week_start,
        accepted_count=accepted_count,
        declined_count=declined_count,
        skipped_count=skipped_count,
        declined_employee_ids=sorted(declined_employee_ids),
        reroll_entries_generated=reroll_entries_generated,
        reroll_notifications_sent=reroll_notifications_sent,
        unfilled_slots=unfilled_slots,
        warnings=warnings[:50],
        summary=summary,
    )


async def commit_month_decisions(
    db: AsyncSession,
    year: int,
    month: int,
    decisions: List[CommitDecision],
    employee_pool: List[str],
    settings: Settings,
) -> CommitDecisionsResult:
    """Bulk-commit scheduler review decisions for a monthly Auto-Gen run."""
    start, end = _month_range(year, month)
    decision_map = {decision.entry_id: decision.keep for decision in decisions}

    if not decision_map:
        summary = await _status_counts(db, start, end, unit_ids=None)
        return CommitDecisionsResult(
            week_start=start,
            accepted_count=0,
            declined_count=0,
            skipped_count=0,
            declined_employee_ids=[],
            summary=summary,
        )

    query = select(ScheduleEntry).where(
        and_(
            ScheduleEntry.id.in_(decision_map.keys()),
            ScheduleEntry.shift_date >= start,
            ScheduleEntry.shift_date <= end,
        )
    )
    entries = list((await db.execute(query)).scalars().all())

    accepted_count = 0
    declined_count = 0
    skipped_count = max(0, len(decision_map) - len(entries))
    declined_employee_ids: set[str] = set()
    now = datetime.now(timezone.utc)

    for entry in entries:
        if entry.confirmation_status != ConfirmationStatus.PENDING:
            skipped_count += 1
            continue

        keep = decision_map.get(entry.id, True)
        await _mark_latest_notification(
            db,
            entry.id,
            NotificationKind.CONFIRM_SHIFT,
            status=NotificationStatus.ACCEPTED if keep else NotificationStatus.DECLINED,
            responded_at=now,
        )

        entry.confirmation_status = (
            ConfirmationStatus.ACCEPTED if keep else ConfirmationStatus.DECLINED
        )
        entry.confirmation_responded_at = now

        if keep:
            accepted_count += 1
        else:
            declined_count += 1
            declined_employee_ids.add(entry.employee_id)

    reroll_entries_generated = 0
    reroll_notifications_sent = 0
    unfilled_slots = 0
    warnings: list[str] = []

    if declined_employee_ids:
        await db.flush()
        reroll_pool = [
            employee_id
            for employee_id in employee_pool
            if employee_id not in declined_employee_ids
        ]
        if reroll_pool:
            regen = await regenerate_month_schedule(
                year=year,
                month=month,
                employee_pool=reroll_pool,
                db=db,
                settings=settings,
                preserve_responded=True,
            )
            sent = await send_month_confirmations(db, year, month, unit_ids=None)
            reroll_entries_generated = regen.entries_created
            reroll_notifications_sent = sent.notifications_created
            unfilled_slots = regen.unfilled_slots
            warnings = regen.warnings
        else:
            await db.commit()
    else:
        await db.commit()

    summary = await _status_counts(db, start, end, unit_ids=None)
    return CommitDecisionsResult(
        week_start=start,
        accepted_count=accepted_count,
        declined_count=declined_count,
        skipped_count=skipped_count,
        declined_employee_ids=sorted(declined_employee_ids),
        reroll_entries_generated=reroll_entries_generated,
        reroll_notifications_sent=reroll_notifications_sent,
        unfilled_slots=unfilled_slots,
        warnings=warnings[:50],
        summary=summary,
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


async def timeout_sweep_entries(
    db: AsyncSession,
    entry_ids: List[int],
) -> TimeoutSweepResult:
    """Bulk-transition PENDING entries to DECLINED as expired.

    Unlike single-entry TIMEOUT via respond_to_confirmation, this does NOT
    generate recommendation payloads synchronously — that would be O(N) LLM
    calls. The supervisor resolves timed-out rows one at a time from the UI
    (Remove from pool, or manually re-trigger replacement).

    Non-PENDING entries are reported in `skipped` instead of raising; the
    sweep is a best-effort bulk call where races with manual Accept/Decline
    are expected.
    """
    now = datetime.now(timezone.utc)
    processed: list[int] = []
    skipped: list[int] = []

    for entry_id in entry_ids:
        entry = await db.get(ScheduleEntry, entry_id)
        if not entry or entry.confirmation_status != ConfirmationStatus.PENDING:
            skipped.append(entry_id)
            continue

        await _mark_latest_notification(
            db,
            entry_id,
            NotificationKind.CONFIRM_SHIFT,
            status=NotificationStatus.TIMEOUT,
            responded_at=now,
        )
        entry.confirmation_status = ConfirmationStatus.DECLINED
        entry.confirmation_responded_at = now
        db.add(
            Callout(
                employee_id=entry.employee_id,
                unit_id=entry.unit_id,
                shift_date=entry.shift_date,
                shift_label=entry.shift_label,
                reason="schedule_decline:timeout",
                reported_at=now,
            )
        )
        processed.append(entry_id)

    await db.commit()
    return TimeoutSweepResult(
        processed=processed, skipped=skipped, processed_at=now
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
