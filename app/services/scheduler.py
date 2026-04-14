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
from app.models.schedule import ScheduleEntry
from app.models.unit import Unit
from app.schemas.common import LicenseType, ShiftLabel, UnitTypology, CERTIFIED_ROLES, LICENSED_ROLES
from app.schemas.schedule import ScheduleGenerationResult
from app.services.filter import (
    CandidateRecord,
    ScheduleContext,
    apply_hard_filters,
)
from app.services.overtime import calculate_ot_headroom
from app.services.scoring import (
    compute_clinical_fit,
    compute_float_penalty,
    load_scoring_config,
    score_candidate,
)
from app.services.shift_utils import SHIFT_DURATION_HOURS
from app.services.staff_loader import (
    build_candidate_records,
    load_exclusions,
    load_hours_map,
    load_staff_pool,
)

logger = structlog.get_logger()

# Max weekly hours — these are scheduling caps, not OT thresholds.
# Staff can be assigned up to 5 shifts/week (FT) or 3 (PT).
# The OT scoring dimension handles financial preference.
FT_WEEKLY_MAX = 41.25  # 5 shifts × 8.25h
PT_WEEKLY_MAX = 24.75  # 3 shifts × 8.25h
PER_DIEM_WEEKLY_MAX = 41.25  # per diem can work up to full-time

# Each unit needs this many staff per shift (demo simplification)
STAFF_PER_SHIFT_LICENSED = 1  # 1 RN/LPN per shift
STAFF_PER_SHIFT_CERTIFIED = 1  # 1 CNA/PCT per shift

SHIFT_ORDER = [ShiftLabel.DAY, ShiftLabel.EVENING, ShiftLabel.NIGHT]


async def generate_monthly_schedule(
    year: int,
    month: int,
    db: AsyncSession,
    settings: Settings,
    staff_count_override: int | None = None,
) -> ScheduleGenerationResult:
    """Generate a full month's schedule, writing ScheduleEntry rows."""

    _, last_day = calendar.monthrange(year, month)
    first = date(year, month, 1)
    last = date(year, month, last_day)

    # Clear ALL existing entries for this month (both published and unpublished)
    # so the scheduler can build from scratch without unique constraint violations
    await db.execute(
        delete(ScheduleEntry).where(
            ScheduleEntry.shift_date.between(first, last),
        )
    )

    # Load all active units
    units_result = await db.execute(select(Unit).where(Unit.is_active == True))
    units = list(units_result.scalars().all())

    # Load staff pool
    staff_list = await load_staff_pool(db)
    all_candidates = build_candidate_records(staff_list)

    # Optional staff reduction for demo scenarios
    if staff_count_override and staff_count_override < len(all_candidates):
        random.seed(42)  # deterministic for demo
        all_candidates = random.sample(all_candidates, staff_count_override)

    # Load scoring config
    scoring_config = load_scoring_config(settings.scoring_weights_path)

    # Load hours map (baseline)
    base_hours_map = await load_hours_map(db)

    # Running state
    running_hours: dict[str, float] = defaultdict(float)
    # Track per-week hours (week = Mon-Sun)
    weekly_hours: dict[tuple[str, int], float] = defaultdict(float)  # (emp_id, week_num) -> hours
    # Track shifts assigned per day per employee for rest-window enforcement
    daily_shifts: dict[tuple[str, date], list[tuple[date, ShiftLabel]]] = defaultdict(list)

    entries_created = 0
    warnings: list[str] = []

    for d in range(1, last_day + 1):
        current_date = date(year, month, d)
        week_num = current_date.isocalendar()[1]

        for unit in units:
            unit_typology = UnitTypology(unit.typology.value)

            for shift_label in SHIFT_ORDER:
                # Staffing model: 1 staff member per unit per shift.
                # Try preferred bucket first, fall back to any available.
                if unit_typology == UnitTypology.SUBACUTE:
                    bucket_order = ["licensed", "certified"]
                else:
                    bucket_order = ["certified", "licensed"]

                assigned = None
                for required_bucket in bucket_order:
                    assigned = _assign_one(
                        candidates=all_candidates,
                        required_bucket=required_bucket,
                        unit=unit,
                        unit_typology=unit_typology,
                        current_date=current_date,
                        shift_label=shift_label,
                        week_num=week_num,
                        weekly_hours=weekly_hours,
                        daily_shifts=daily_shifts,
                        base_hours_map=base_hours_map,
                        scoring_config=scoring_config,
                        settings=settings,
                        db=db,
                    )
                    if assigned:
                        break  # filled from this bucket, no need to try fallback

                if assigned:
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

                    # Update running state
                    running_hours[emp_id] += SHIFT_DURATION_HOURS
                    weekly_hours[(emp_id, week_num)] += SHIFT_DURATION_HOURS
                    daily_shifts[(emp_id, current_date)].append(
                        (current_date, shift_label)
                    )
                else:
                    warnings.append(
                        f"Unfilled: {unit.unit_id} {shift_label.value} {current_date}"
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


def _assign_one(
    candidates: list[CandidateRecord],
    required_bucket: str,
    unit: Unit,
    unit_typology: UnitTypology,
    current_date: date,
    shift_label: ShiftLabel,
    week_num: int,
    weekly_hours: dict[tuple[str, int], float],
    daily_shifts: dict[tuple[str, date], list[tuple[date, ShiftLabel]]],
    base_hours_map: dict,
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

    # Additional: filter by weekly hours budget
    survivors = []
    for cand in filter_result.passed:
        emp_id = cand.employee_id
        current_weekly = weekly_hours.get((emp_id, week_num), 0.0)
        if cand.employment_class == "FT":
            max_hours = FT_WEEKLY_MAX
        elif cand.employment_class == "PER_DIEM":
            max_hours = PER_DIEM_WEEKLY_MAX
        else:
            max_hours = PT_WEEKLY_MAX
        if current_weekly + SHIFT_DURATION_HOURS <= max_hours:
            survivors.append(cand)

    if not survivors:
        return None

    # Score and pick the best
    best_cand = None
    best_score = -999.0

    for cand in survivors:
        hours_rec = base_hours_map.get(cand.employee_id)
        hours_this_cycle = (hours_rec.hours_this_cycle if hours_rec else 0.0) + weekly_hours.get((cand.employee_id, week_num), 0.0)
        shift_count_biweek = (hours_rec.shift_count_this_biweek if hours_rec else 0)

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
