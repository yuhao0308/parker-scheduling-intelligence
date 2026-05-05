"""Monthly auto-scheduler: generates a full month of schedule entries.

Processes each day/unit/shift sequentially, reusing the existing filter
and scoring pipeline. Tracks running hours to prevent over-assignment.
"""

from __future__ import annotations

import calendar
import random
from collections import defaultdict
from datetime import date, timedelta

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.integrations.timeclock.kronos_schema import PayCode
from app.integrations.timeclock.source import CSVSource
from app.models.hours import HoursLedger
from app.models.notification import SimulatedNotification
from app.models.schedule import ConfirmationStatus, ScheduleEntry
from app.models.unit import Unit
from app.schemas.common import LicenseType, ShiftLabel, UnitTypology, CERTIFIED_ROLES, LICENSED_ROLES
from app.schemas.schedule import RegenerateWeekResult, ScheduleGenerationResult
from app.services.filter import (
    CandidateRecord,
    ScheduleContext,
    apply_hard_filters,
)
from app.services.overtime import (
    BIWEEKLY_SHIFT_OT_THRESHOLD,
    WEEKLY_OT_THRESHOLD_HOURS,
    calculate_ot_headroom,
)
from app.services.scoring import (
    compute_clinical_fit,
    compute_float_penalty,
    load_scoring_config,
    score_candidate,
)
from app.services.staffing_requirements import slot_requirements
from app.services.staff_loader import (
    build_candidate_records,
    load_staff_pool,
)
from app.services.shift_utils import SHIFT_DURATION_HOURS, is_rn_daily_ot

logger = structlog.get_logger()

# Max weekly hours — these are scheduling caps, not OT thresholds.
# Staff can be assigned up to 5 shifts/week (FT) or 3 (PT).
# The OT scoring dimension handles financial preference.
FT_WEEKLY_MAX = 41.25  # 5 shifts × 8.25h
PT_WEEKLY_MAX = 24.75  # 3 shifts × 8.25h
PER_DIEM_WEEKLY_MAX = 41.25  # per diem can work up to full-time

SHIFT_ORDER = [ShiftLabel.DAY, ShiftLabel.EVENING, ShiftLabel.NIGHT]

BIWEEKLY_CYCLE_DAYS = 14
BIWEEKLY_CYCLE_ANCHOR = date(2026, 3, 30)
PRODUCTIVE_PAY_CODES = {PayCode.REG, PayCode.OT, PayCode.DT, PayCode.HOL}


def _biweekly_cycle_start(value: date) -> date:
    delta_days = (value - BIWEEKLY_CYCLE_ANCHOR).days
    if delta_days >= 0:
        offset = (delta_days // BIWEEKLY_CYCLE_DAYS) * BIWEEKLY_CYCLE_DAYS
    else:
        offset = -(
            ((-delta_days + BIWEEKLY_CYCLE_DAYS - 1) // BIWEEKLY_CYCLE_DAYS)
            * BIWEEKLY_CYCLE_DAYS
        )
    return BIWEEKLY_CYCLE_ANCHOR + timedelta(days=offset)


async def _load_hours_by_cycle(
    db: AsyncSession,
) -> dict[tuple[str, date], HoursLedger]:
    result = await db.execute(select(HoursLedger))
    return {
        (row.employee_id, row.cycle_start_date): row
        for row in result.scalars().all()
    }


async def _load_weekly_actual_hours(
    start: date,
    end: date,
    *,
    as_of: date | None = None,
) -> dict[tuple[str, int], float]:
    today = as_of or date.today()
    if start > today:
        return {}

    try:
        totals = await CSVSource().fetch_daily_totals(start, min(end, today))
    except FileNotFoundError:
        return {}

    weekly_hours: dict[tuple[str, int], float] = defaultdict(float)
    for total in totals:
        if total.pay_code not in PRODUCTIVE_PAY_CODES:
            continue
        week_num = total.work_date.isocalendar()[1]
        weekly_hours[(total.person_number, week_num)] += total.hours
    return dict(weekly_hours)


def _weekly_max_for(candidate: CandidateRecord) -> float:
    if candidate.employment_class == "FT":
        return FT_WEEKLY_MAX
    if candidate.employment_class == "PER_DIEM":
        return PER_DIEM_WEEKLY_MAX
    return PT_WEEKLY_MAX


async def generate_monthly_schedule(
    year: int,
    month: int,
    db: AsyncSession,
    settings: Settings,
    staff_count_override: int | None = None,
    employee_pool: list[str] | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> ScheduleGenerationResult:
    """Generate a schedule for either a calendar month or a 4-week period.

    By default the function generates the full calendar month identified by
    ``year``/``month``. When ``period_start`` and ``period_end`` are provided
    they override the month bounds — every day in the inclusive range is
    iterated. ``year``/``month`` are still used by callers downstream
    (logging, response payload).

    When ``employee_pool`` is provided, only those employees are eligible for
    assignment. ``staff_count_override`` is ignored in that case (pool is the
    source of truth)."""

    if period_start is not None and period_end is not None:
        first = period_start
        last = period_end
    else:
        _, last_day = calendar.monthrange(year, month)
        first = date(year, month, 1)
        last = date(year, month, last_day)
    query_start = first - timedelta(days=first.isocalendar().weekday - 1)
    query_end = last + timedelta(days=7 - last.isocalendar().weekday)

    # Clear ALL existing entries for this month (both published and unpublished)
    # so the scheduler can build from scratch without unique constraint violations.
    # Clear dependent simulated_notification rows first to avoid FK violations.
    entry_ids_result = await db.execute(
        select(ScheduleEntry.id).where(
            ScheduleEntry.shift_date.between(first, last),
        )
    )
    entry_ids = list(entry_ids_result.scalars().all())
    if entry_ids:
        await db.execute(
            delete(SimulatedNotification).where(
                SimulatedNotification.schedule_entry_id.in_(entry_ids)
            )
        )
    await db.execute(
        delete(ScheduleEntry).where(
            ScheduleEntry.shift_date.between(first, last),
        )
    )

    # Load all active units
    units_result = await db.execute(select(Unit).where(Unit.is_active == True))
    units = sorted(
        units_result.scalars().all(),
        key=lambda unit: (
            0 if UnitTypology(unit.typology.value) == UnitTypology.SUBACUTE else 1,
            unit.unit_id,
        ),
    )

    # Load staff pool
    staff_list = await load_staff_pool(db)
    all_candidates = build_candidate_records(staff_list)

    if employee_pool:
        pool_set = set(employee_pool)
        all_candidates = [c for c in all_candidates if c.employee_id in pool_set]
    elif staff_count_override and staff_count_override < len(all_candidates):
        # Optional staff reduction for demo scenarios when no explicit pool.
        random.seed(42)  # deterministic for demo
        all_candidates = random.sample(all_candidates, staff_count_override)

    # Load scoring config
    scoring_config = load_scoring_config(settings.scoring_weights_path)

    base_hours_by_cycle = await _load_hours_by_cycle(db)

    # Running state
    weekly_hours: dict[tuple[str, int], float] = defaultdict(float)  # (emp_id, week_num) -> hours
    weekly_hours.update(await _load_weekly_actual_hours(query_start, query_end))
    biweekly_shifts: dict[tuple[str, date], int] = defaultdict(int)
    # Track shifts assigned per day per employee for rest-window enforcement
    daily_shifts: dict[tuple[str, date], list[tuple[date, ShiftLabel]]] = defaultdict(list)

    entries_created = 0
    warnings: list[str] = []

    total_days = (last - first).days + 1
    for offset in range(total_days):
        current_date = first + timedelta(days=offset)
        week_num = current_date.isocalendar()[1]

        for unit in units:
            unit_typology = UnitTypology(unit.typology.value)

            for shift_label in SHIFT_ORDER:
                requirements = slot_requirements(unit, shift_label)
                if unit_typology == UnitTypology.SUBACUTE:
                    bucket_order = [
                        ("licensed", requirements.licensed),
                        ("certified", requirements.certified),
                    ]
                else:
                    bucket_order = [
                        ("certified", requirements.certified),
                        ("licensed", requirements.licensed),
                    ]

                for required_bucket, count_needed in bucket_order:
                    for ordinal in range(1, count_needed + 1):
                        assigned = _assign_one(
                            candidates=all_candidates,
                            required_bucket=required_bucket,
                            unit=unit,
                            unit_typology=unit_typology,
                            current_date=current_date,
                            shift_label=shift_label,
                            week_num=week_num,
                            weekly_hours=weekly_hours,
                            biweekly_shifts=biweekly_shifts,
                            daily_shifts=daily_shifts,
                            base_hours_by_cycle=base_hours_by_cycle,
                            scoring_config=scoring_config,
                            settings=settings,
                            db=db,
                        )

                        if not assigned:
                            warnings.append(
                                f"Unfilled: {unit.unit_id} {shift_label.value} "
                                f"{current_date} [{required_bucket} #{ordinal}]"
                            )
                            continue

                        emp_id = assigned.employee_id
                        entry = ScheduleEntry(
                            employee_id=emp_id,
                            unit_id=unit.unit_id,
                            shift_date=current_date,
                            shift_label=shift_label,
                            is_published=False,
                        )
                        db.add(entry)
                        entries_created += 1

                        weekly_hours[(emp_id, week_num)] += SHIFT_DURATION_HOURS
                        biweekly_shifts[
                            (emp_id, _biweekly_cycle_start(current_date))
                        ] += 1
                        daily_shifts[(emp_id, current_date)].append(
                            (current_date, shift_label)
                        )

    await db.commit()

    unfilled = len(warnings)
    total_slots = entries_created + unfilled
    unfilled_pct = (unfilled / total_slots * 100) if total_slots > 0 else 0
    if unfilled == 0:
        scenario = "ideal"
    elif unfilled_pct <= 10:
        scenario = "moderate"
    else:
        scenario = "critical"

    logger.info(
        "schedule_generated",
        year=year,
        month=month,
        entries_created=entries_created,
        unfilled=unfilled,
        scenario=scenario,
    )

    return ScheduleGenerationResult(
        entries_created=entries_created,
        warnings=warnings[:50],  # cap for response size
        scenario=scenario,
        unfilled_slots=unfilled,
    )


async def regenerate_week_schedule(
    week_start: date,
    employee_pool: list[str],
    db: AsyncSession,
    settings: Settings,
    preserve_responded: bool = True,
) -> RegenerateWeekResult:
    """Regenerate the 7-day window starting at ``week_start``.

    Preserves any ``ScheduleEntry`` whose confirmation_status is ACCEPTED
    (and, when ``preserve_responded`` is true, PENDING) — those nurses
    already either said yes or are mid-ask. Drops UNSENT/DECLINED/REPLACED
    rows and re-solves only the remaining gaps using the supplied pool.

    The pool is an allowlist: no one outside ``employee_pool`` will be
    assigned, even if they'd otherwise score well. ACCEPTED employees
    stay on their frozen slot even if they're not in the new pool —
    the scheduler can't silently delete a confirmed shift.
    """
    week_end = week_start + timedelta(days=6)

    preserved_statuses = [ConfirmationStatus.ACCEPTED]
    if preserve_responded:
        preserved_statuses.append(ConfirmationStatus.PENDING)

    # Load entries in the window, partition into preserved vs. removable.
    existing_result = await db.execute(
        select(ScheduleEntry).where(
            ScheduleEntry.shift_date.between(week_start, week_end),
        )
    )
    existing = list(existing_result.scalars().all())
    preserved = [e for e in existing if e.confirmation_status in preserved_statuses]

    # Delete everything else (UNSENT/DECLINED/REPLACED) to clear gaps.
    removable_ids = [e.id for e in existing if e.confirmation_status not in preserved_statuses]
    if removable_ids:
        # Clear dependent notifications first — FK prevents deleting schedule
        # entries that are still referenced by simulated_notification rows.
        await db.execute(
            delete(SimulatedNotification).where(
                SimulatedNotification.schedule_entry_id.in_(removable_ids)
            )
        )
        await db.execute(
            delete(ScheduleEntry).where(ScheduleEntry.id.in_(removable_ids))
        )

    # Pre-seed running state from preserved entries so hour budgets & rest
    # windows account for already-accepted shifts.
    weekly_hours: dict[tuple[str, int], float] = defaultdict(float)
    weekly_hours.update(await _load_weekly_actual_hours(week_start, week_end))
    biweekly_shifts: dict[tuple[str, date], int] = defaultdict(int)
    daily_shifts: dict[tuple[str, date], list[tuple[date, ShiftLabel]]] = defaultdict(list)
    for e in preserved:
        label = e.shift_label if isinstance(e.shift_label, ShiftLabel) else ShiftLabel(e.shift_label.value)
        wk = e.shift_date.isocalendar()[1]
        weekly_hours[(e.employee_id, wk)] += SHIFT_DURATION_HOURS
        biweekly_shifts[(e.employee_id, _biweekly_cycle_start(e.shift_date))] += 1
        daily_shifts[(e.employee_id, e.shift_date)].append((e.shift_date, label))

    # Load units
    units_result = await db.execute(select(Unit).where(Unit.is_active == True))
    units = sorted(
        units_result.scalars().all(),
        key=lambda unit: (
            0 if UnitTypology(unit.typology.value) == UnitTypology.SUBACUTE else 1,
            unit.unit_id,
        ),
    )

    staff_list = await load_staff_pool(db)
    all_staff_candidates = build_candidate_records(staff_list)
    staff_by_id = {c.employee_id: c for c in all_staff_candidates}
    pool_set = set(employee_pool)
    all_candidates = [c for c in all_staff_candidates if c.employee_id in pool_set]

    preserved_counts: dict[tuple[date, str, ShiftLabel], dict[str, int]] = defaultdict(
        lambda: {"licensed": 0, "certified": 0}
    )
    for e in preserved:
        label = e.shift_label if isinstance(e.shift_label, ShiftLabel) else ShiftLabel(e.shift_label.value)
        staff = staff_by_id.get(e.employee_id)
        if not staff:
            continue
        bucket = "licensed" if staff.license in LICENSED_ROLES else "certified"
        preserved_counts[(e.shift_date, e.unit_id, label)][bucket] += 1

    scoring_config = load_scoring_config(settings.scoring_weights_path)
    base_hours_by_cycle = await _load_hours_by_cycle(db)

    entries_created = 0
    warnings: list[str] = []

    for day_offset in range(7):
        current_date = week_start + timedelta(days=day_offset)
        week_num = current_date.isocalendar()[1]

        for unit in units:
            unit_typology = UnitTypology(unit.typology.value)

            for shift_label in SHIFT_ORDER:
                requirements = slot_requirements(unit, shift_label)
                key = (current_date, unit.unit_id, shift_label)
                preserved_for_slot = preserved_counts.get(
                    key, {"licensed": 0, "certified": 0}
                )
                if unit_typology == UnitTypology.SUBACUTE:
                    bucket_order = [
                        (
                            "licensed",
                            max(0, requirements.licensed - preserved_for_slot["licensed"]),
                        ),
                        (
                            "certified",
                            max(0, requirements.certified - preserved_for_slot["certified"]),
                        ),
                    ]
                else:
                    bucket_order = [
                        (
                            "certified",
                            max(0, requirements.certified - preserved_for_slot["certified"]),
                        ),
                        (
                            "licensed",
                            max(0, requirements.licensed - preserved_for_slot["licensed"]),
                        ),
                    ]

                for required_bucket, count_needed in bucket_order:
                    for ordinal in range(1, count_needed + 1):
                        assigned = _assign_one(
                            candidates=all_candidates,
                            required_bucket=required_bucket,
                            unit=unit,
                            unit_typology=unit_typology,
                            current_date=current_date,
                            shift_label=shift_label,
                            week_num=week_num,
                            weekly_hours=weekly_hours,
                            biweekly_shifts=biweekly_shifts,
                            daily_shifts=daily_shifts,
                            base_hours_by_cycle=base_hours_by_cycle,
                            scoring_config=scoring_config,
                            settings=settings,
                            db=db,
                        )
                        if not assigned:
                            warnings.append(
                                f"Unfilled: {unit.unit_id} {shift_label.value} "
                                f"{current_date} [{required_bucket} #{ordinal}]"
                            )
                            continue

                        emp_id = assigned.employee_id
                        entry = ScheduleEntry(
                            employee_id=emp_id,
                            unit_id=unit.unit_id,
                            shift_date=current_date,
                            shift_label=shift_label,
                            is_published=False,
                            confirmation_status=ConfirmationStatus.UNSENT,
                        )
                        db.add(entry)
                        entries_created += 1

                        weekly_hours[(emp_id, week_num)] += SHIFT_DURATION_HOURS
                        biweekly_shifts[
                            (emp_id, _biweekly_cycle_start(current_date))
                        ] += 1
                        daily_shifts[(emp_id, current_date)].append(
                            (current_date, shift_label)
                        )

    await db.commit()

    logger.info(
        "week_regenerated",
        week_start=week_start.isoformat(),
        pool_size=len(pool_set),
        entries_created=entries_created,
        entries_preserved=len(preserved),
        unfilled=len(warnings),
    )

    return RegenerateWeekResult(
        week_start=week_start,
        entries_created=entries_created,
        entries_preserved=len(preserved),
        warnings=warnings[:50],
        unfilled_slots=len(warnings),
    )


async def regenerate_month_schedule(
    year: int,
    month: int,
    employee_pool: list[str],
    db: AsyncSession,
    settings: Settings,
    preserve_responded: bool = True,
) -> ScheduleGenerationResult:
    """Regenerate a full month while preserving reviewed/pending entries."""
    _, last_day = calendar.monthrange(year, month)
    first = date(year, month, 1)
    last = date(year, month, last_day)

    preserved_statuses = [ConfirmationStatus.ACCEPTED]
    if preserve_responded:
        preserved_statuses.append(ConfirmationStatus.PENDING)

    existing_result = await db.execute(
        select(ScheduleEntry).where(ScheduleEntry.shift_date.between(first, last))
    )
    existing = list(existing_result.scalars().all())
    preserved = [e for e in existing if e.confirmation_status in preserved_statuses]

    removable_ids = [e.id for e in existing if e.confirmation_status not in preserved_statuses]
    if removable_ids:
        await db.execute(
            delete(SimulatedNotification).where(
                SimulatedNotification.schedule_entry_id.in_(removable_ids)
            )
        )
        await db.execute(delete(ScheduleEntry).where(ScheduleEntry.id.in_(removable_ids)))

    weekly_hours: dict[tuple[str, int], float] = defaultdict(float)
    weekly_hours.update(await _load_weekly_actual_hours(query_start, query_end))
    biweekly_shifts: dict[tuple[str, date], int] = defaultdict(int)
    daily_shifts: dict[tuple[str, date], list[tuple[date, ShiftLabel]]] = defaultdict(list)
    for e in preserved:
        label = e.shift_label if isinstance(e.shift_label, ShiftLabel) else ShiftLabel(e.shift_label.value)
        wk = e.shift_date.isocalendar()[1]
        weekly_hours[(e.employee_id, wk)] += SHIFT_DURATION_HOURS
        biweekly_shifts[(e.employee_id, _biweekly_cycle_start(e.shift_date))] += 1
        daily_shifts[(e.employee_id, e.shift_date)].append((e.shift_date, label))

    units_result = await db.execute(select(Unit).where(Unit.is_active == True))
    units = sorted(
        units_result.scalars().all(),
        key=lambda unit: (
            0 if UnitTypology(unit.typology.value) == UnitTypology.SUBACUTE else 1,
            unit.unit_id,
        ),
    )

    staff_list = await load_staff_pool(db)
    all_staff_candidates = build_candidate_records(staff_list)
    staff_by_id = {c.employee_id: c for c in all_staff_candidates}
    pool_set = set(employee_pool)
    all_candidates = [c for c in all_staff_candidates if c.employee_id in pool_set]

    preserved_counts: dict[tuple[date, str, ShiftLabel], dict[str, int]] = defaultdict(
        lambda: {"licensed": 0, "certified": 0}
    )
    for e in preserved:
        label = e.shift_label if isinstance(e.shift_label, ShiftLabel) else ShiftLabel(e.shift_label.value)
        staff = staff_by_id.get(e.employee_id)
        if not staff:
            continue
        bucket = "licensed" if staff.license in LICENSED_ROLES else "certified"
        preserved_counts[(e.shift_date, e.unit_id, label)][bucket] += 1

    scoring_config = load_scoring_config(settings.scoring_weights_path)
    base_hours_by_cycle = await _load_hours_by_cycle(db)

    entries_created = 0
    warnings: list[str] = []

    for d in range(1, last_day + 1):
        current_date = date(year, month, d)
        week_num = current_date.isocalendar()[1]

        for unit in units:
            unit_typology = UnitTypology(unit.typology.value)

            for shift_label in SHIFT_ORDER:
                requirements = slot_requirements(unit, shift_label)
                key = (current_date, unit.unit_id, shift_label)
                preserved_for_slot = preserved_counts.get(
                    key, {"licensed": 0, "certified": 0}
                )
                if unit_typology == UnitTypology.SUBACUTE:
                    bucket_order = [
                        (
                            "licensed",
                            max(0, requirements.licensed - preserved_for_slot["licensed"]),
                        ),
                        (
                            "certified",
                            max(0, requirements.certified - preserved_for_slot["certified"]),
                        ),
                    ]
                else:
                    bucket_order = [
                        (
                            "certified",
                            max(0, requirements.certified - preserved_for_slot["certified"]),
                        ),
                        (
                            "licensed",
                            max(0, requirements.licensed - preserved_for_slot["licensed"]),
                        ),
                    ]

                for required_bucket, count_needed in bucket_order:
                    for ordinal in range(1, count_needed + 1):
                        assigned = _assign_one(
                            candidates=all_candidates,
                            required_bucket=required_bucket,
                            unit=unit,
                            unit_typology=unit_typology,
                            current_date=current_date,
                            shift_label=shift_label,
                            week_num=week_num,
                            weekly_hours=weekly_hours,
                            biweekly_shifts=biweekly_shifts,
                            daily_shifts=daily_shifts,
                            base_hours_by_cycle=base_hours_by_cycle,
                            scoring_config=scoring_config,
                            settings=settings,
                            db=db,
                        )
                        if not assigned:
                            warnings.append(
                                f"Unfilled: {unit.unit_id} {shift_label.value} "
                                f"{current_date} [{required_bucket} #{ordinal}]"
                            )
                            continue

                        emp_id = assigned.employee_id
                        entry = ScheduleEntry(
                            employee_id=emp_id,
                            unit_id=unit.unit_id,
                            shift_date=current_date,
                            shift_label=shift_label,
                            is_published=False,
                            confirmation_status=ConfirmationStatus.UNSENT,
                        )
                        db.add(entry)
                        entries_created += 1

                        weekly_hours[(emp_id, week_num)] += SHIFT_DURATION_HOURS
                        biweekly_shifts[
                            (emp_id, _biweekly_cycle_start(current_date))
                        ] += 1
                        daily_shifts[(emp_id, current_date)].append(
                            (current_date, shift_label)
                        )

    await db.commit()

    unfilled = len(warnings)
    total_slots = entries_created + unfilled
    unfilled_pct = (unfilled / total_slots * 100) if total_slots > 0 else 0
    if unfilled == 0:
        scenario = "ideal"
    elif unfilled_pct <= 10:
        scenario = "moderate"
    else:
        scenario = "critical"

    logger.info(
        "month_regenerated",
        year=year,
        month=month,
        pool_size=len(pool_set),
        entries_created=entries_created,
        entries_preserved=len(preserved),
        unfilled=unfilled,
    )

    return ScheduleGenerationResult(
        entries_created=entries_created,
        warnings=warnings[:50],
        scenario=scenario,
        unfilled_slots=unfilled,
    )


def _assign_one(
    candidates: list[CandidateRecord],
    required_bucket: str,
    unit: Unit,
    unit_typology: UnitTypology,
    current_date: date,
    shift_label: ShiftLabel,
    week_num: int,
    weekly_hours: dict[tuple[str, int], float],
    biweekly_shifts: dict[tuple[str, date], int],
    daily_shifts: dict[tuple[str, date], list[tuple[date, ShiftLabel]]],
    base_hours_by_cycle: dict[tuple[str, date], HoursLedger],
    scoring_config,
    settings: Settings,
    db: AsyncSession,
) -> CandidateRecord | None:
    """Try to assign one staff member to the slot. Returns the assigned candidate or None."""

    # Filter by license bucket
    if required_bucket == "licensed":
        allowed = LICENSED_ROLES
    else:
        allowed = CERTIFIED_ROLES

    bucket_candidates = [c for c in candidates if c.license in allowed]

    # Build a minimal schedule context from in-memory state
    employee_shifts_map: dict[str, list[tuple[date, ShiftLabel]]] = defaultdict(list)
    employees_scheduled: set[str] = set()

    for cand in bucket_candidates:
        emp_id = cand.employee_id
        # Collect shifts from ±1 day for rest window check
        for delta in [-1, 0, 1]:
            check_date = current_date + timedelta(days=delta)
            shifts = daily_shifts.get((emp_id, check_date), [])
            employee_shifts_map[emp_id].extend(shifts)

        # Check if already scheduled for this exact slot
        for s_date, s_label in daily_shifts.get((emp_id, current_date), []):
            if s_date == current_date and s_label == shift_label:
                employees_scheduled.add(emp_id)

    schedule_ctx = ScheduleContext(
        employee_shifts=employee_shifts_map,
        employees_on_pto=set(),
        employees_scheduled=employees_scheduled,
    )

    # Apply hard filters
    filter_result = apply_hard_filters(
        candidates=bucket_candidates,
        required_license=list(allowed)[0],  # any from bucket
        schedule=schedule_ctx,
        exclusions=[],
        target_unit_id=unit.unit_id,
        target_date=current_date,
        target_label=shift_label,
    )

    # Additional: prefer candidates who can take the shift without triggering
    # the overtime rule for their role. If coverage requires it, fall back to
    # the broader scheduling cap rather than leaving the slot unfilled.
    safe_survivors = []
    fallback_survivors = []
    for cand in filter_result.passed:
        emp_id = cand.employee_id
        current_weekly = weekly_hours.get((emp_id, week_num), 0.0)
        max_hours = _weekly_max_for(cand)
        if current_weekly + SHIFT_DURATION_HOURS <= max_hours:
            fallback_survivors.append(cand)

            if cand.license == LicenseType.RN:
                cycle_start = _biweekly_cycle_start(current_date)
                base_hours = base_hours_by_cycle.get((emp_id, cycle_start))
                existing_biweekly_shifts = (
                    base_hours.shift_count_this_biweek if base_hours else 0
                ) + biweekly_shifts.get((emp_id, cycle_start), 0)
                would_daily_ot = is_rn_daily_ot(
                    employee_shifts_map.get(emp_id, []),
                    current_date,
                    shift_label,
                )
                if (
                    not would_daily_ot
                    and existing_biweekly_shifts + 1 <= BIWEEKLY_SHIFT_OT_THRESHOLD
                ):
                    safe_survivors.append(cand)
            elif current_weekly + SHIFT_DURATION_HOURS <= min(
                max_hours,
                WEEKLY_OT_THRESHOLD_HOURS,
            ):
                safe_survivors.append(cand)

    survivors = safe_survivors or fallback_survivors

    if not survivors:
        return None

    # Score and pick the best
    best_cand = None
    best_score = -999.0

    for cand in survivors:
        if cand.license == LicenseType.RN:
            cycle_start = _biweekly_cycle_start(current_date)
            hours_rec = base_hours_by_cycle.get((cand.employee_id, cycle_start))
            assigned_cycle_shifts = biweekly_shifts.get(
                (cand.employee_id, cycle_start),
                0,
            )
            hours_this_cycle = (
                (hours_rec.hours_this_cycle if hours_rec else 0.0)
                + assigned_cycle_shifts * SHIFT_DURATION_HOURS
            )
            shift_count_biweek = (
                (hours_rec.shift_count_this_biweek if hours_rec else 0)
                + assigned_cycle_shifts
            )
        else:
            hours_this_cycle = weekly_hours.get((cand.employee_id, week_num), 0.0)
            shift_count_biweek = 0

        employee_shifts = employee_shifts_map.get(cand.employee_id, [])

        ot_headroom, _ = calculate_ot_headroom(
            license_type=cand.license,
            hours_this_cycle=hours_this_cycle,
            shift_count_this_biweek=shift_count_biweek,
            employee_shifts=employee_shifts,
            target_date=current_date,
            target_label=shift_label,
        )

        clin_fit = compute_clinical_fit(
            candidate_home_typology=UnitTypology(cand.home_unit_typology),
            candidate_cross_trained_unit_ids=cand.cross_trained_unit_ids,
            target_unit_id=unit.unit_id,
            target_typology=unit_typology,
            home_unit_id=cand.home_unit_id,
            config=scoring_config,
        )

        float_pen = compute_float_penalty(
            home_unit_id=cand.home_unit_id,
            target_unit_id=unit.unit_id,
            candidate_home_typology=UnitTypology(cand.home_unit_typology),
            target_typology=unit_typology,
            hire_date=cand.hire_date,
            reference_date=current_date,
            config=scoring_config,
        )

        result = score_candidate(
            ot_headroom=ot_headroom,
            proximity=0.5,  # not relevant for batch scheduling
            clinical_fit=clin_fit,
            float_penalty=float_pen,
            weights=scoring_config.weights,
        )

        if result.total > best_score:
            best_score = result.total
            best_cand = cand

    return best_cand
