"""Shared DB helpers for loading staff, schedule context, and hours data.

Extracted from recommendation.py so that both the recommendation pipeline
and the monthly scheduler can reuse the same data-loading logic.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.exclusion import UnitExclusion
from app.models.hours import HoursLedger
from app.models.schedule import PTOEntry, ScheduleEntry
from app.models.staff import StaffMaster
from app.models.unit import Unit
from app.schemas.common import LicenseType, ShiftLabel
from app.services.filter import CandidateRecord, ExclusionRecord, ScheduleContext


@dataclass
class MonthScheduleMetrics:
    """Per-employee snapshot of the calendar month containing the call-out.

    Mirrors the same numbers the workload monitor surfaces so that rationale
    text and the monitor never disagree.
    """

    scheduled_shifts: int = 0
    scheduled_hours: float = 0.0
    home_unit_shifts: int = 0
    float_shifts: int = 0
    peak_week_hours: float = 0.0
    peak_biweekly_shifts: int = 0
    projected_overtime_hours: float = 0.0
    projected_overtime_shifts: int = 0
    double_shift_days: int = 0
    # Callout-context signals (only populated when target_unit_id /
    # target_date are supplied to ``load_month_schedule_metrics``).
    target_unit_shifts: int = 0
    has_adjacent_shift: bool = False


async def load_staff_pool(db: AsyncSession) -> list[dict]:
    """Load all active staff with their ops and cross-training data."""
    result = await db.execute(
        select(StaffMaster)
        .where(StaffMaster.is_active == True)
        .options(
            selectinload(StaffMaster.ops),
            selectinload(StaffMaster.cross_trainings),
        )
    )
    staff_rows = result.scalars().all()

    pool = []
    for s in staff_rows:
        if not s.ops:
            continue

        home_unit = await db.get(Unit, s.ops.home_unit_id)
        home_typology = home_unit.typology.value if home_unit else "LT"

        pool.append(
            {
                "employee_id": s.employee_id,
                "name": s.name,
                "license": s.license,
                "employment_class": s.employment_class.value,
                "zip_code": s.zip_code,
                "home_unit_id": s.ops.home_unit_id,
                "home_unit_typology": home_typology,
                "cross_trained_unit_ids": [ct.unit_id for ct in s.cross_trainings],
                "hire_date": s.ops.hire_date,
                "is_active": s.is_active,
            }
        )
    return pool


def build_candidate_records(staff_list: list[dict]) -> list[CandidateRecord]:
    """Convert raw staff dicts to CandidateRecord objects."""
    return [
        CandidateRecord(
            employee_id=s["employee_id"],
            name=s["name"],
            license=LicenseType(s["license"].value if hasattr(s["license"], "value") else s["license"]),
            employment_class=s["employment_class"],
            zip_code=s["zip_code"],
            home_unit_id=s["home_unit_id"],
            home_unit_typology=s["home_unit_typology"],
            cross_trained_unit_ids=s["cross_trained_unit_ids"],
            hire_date=s["hire_date"],
            is_active=s["is_active"],
        )
        for s in staff_list
    ]


async def build_schedule_context(
    db: AsyncSession, target_date: date, target_label: ShiftLabel
) -> ScheduleContext:
    """Build schedule context for filtering."""
    date_range_start = target_date - timedelta(days=1)
    date_range_end = target_date + timedelta(days=1)

    from app.models.schedule import ConfirmationStatus

    result = await db.execute(
        select(ScheduleEntry).where(
            ScheduleEntry.shift_date.between(date_range_start, date_range_end),
            ScheduleEntry.confirmation_status != ConfirmationStatus.REPLACED,
        )
    )
    entries = result.scalars().all()

    employee_shifts: dict[str, list[tuple[date, ShiftLabel]]] = {}
    employees_scheduled: set[str] = set()
    unit_shift_license_counts: dict[
        tuple[str, date, ShiftLabel], dict[LicenseType, int]
    ] = {}

    # Lazy staff license lookup for coverage counts
    staff_license_rows = await db.execute(select(StaffMaster.employee_id, StaffMaster.license))
    staff_license_map: dict[str, LicenseType] = {
        eid: LicenseType(lic.value) for eid, lic in staff_license_rows.all()
    }

    for e in entries:
        label = ShiftLabel(e.shift_label.value)
        employee_shifts.setdefault(e.employee_id, []).append((e.shift_date, label))
        if e.shift_date == target_date and label == target_label:
            employees_scheduled.add(e.employee_id)

        lic = staff_license_map.get(e.employee_id)
        if lic is not None:
            key = (e.unit_id, e.shift_date, label)
            bucket = unit_shift_license_counts.setdefault(key, {})
            bucket[lic] = bucket.get(lic, 0) + 1

    pto_result = await db.execute(
        select(PTOEntry).where(
            PTOEntry.start_date <= target_date,
            PTOEntry.end_date >= target_date,
        )
    )
    employees_on_pto = {p.employee_id for p in pto_result.scalars().all()}

    return ScheduleContext(
        employee_shifts=employee_shifts,
        employees_on_pto=employees_on_pto,
        employees_scheduled=employees_scheduled,
        unit_shift_license_counts=unit_shift_license_counts,
    )


async def load_unit_minimums(
    db: AsyncSession,
) -> tuple[dict[str, int], dict[str, int]]:
    """Load per-unit regulatory minimums derived from typology.

    Per United Hebrew spec:
      - Long-Term units: >=1 licensed nurse per shift
      - Short-Term (SUBACUTE) units: >=2 licensed nurses per shift
      - Certified staff: ratio approx 1 CNA per 10 residents (baseline 4 CNAs
        for a 40-resident unit). Stored on Unit.required_ratio (staff count).
    """
    result = await db.execute(select(Unit))
    min_licensed: dict[str, int] = {}
    min_certified: dict[str, int] = {}
    for u in result.scalars().all():
        typ = u.typology.value if hasattr(u.typology, "value") else u.typology
        min_licensed[u.unit_id] = 2 if typ == "SUBACUTE" else 1
        # required_ratio is expected to hold the baseline CNA count per shift
        # (e.g. 4 for a 40-resident unit). Default to 4 if unset.
        try:
            min_certified[u.unit_id] = int(u.required_ratio) if u.required_ratio else 4
        except (TypeError, ValueError):
            min_certified[u.unit_id] = 4
    return min_licensed, min_certified


async def load_exclusions(
    db: AsyncSession, target_unit_id: str, target_date: date
) -> list[ExclusionRecord]:
    """Load active exclusions for the target unit."""
    result = await db.execute(
        select(UnitExclusion).where(UnitExclusion.unit_id == target_unit_id)
    )
    exclusions = []
    for exc in result.scalars().all():
        exclusions.append(
            ExclusionRecord(
                employee_id=exc.employee_id,
                unit_id=exc.unit_id,
                effective_from=exc.effective_from,
                effective_until=exc.effective_until,
            )
        )
    return exclusions


async def load_last_shift_dates(
    db: AsyncSession, as_of: date
) -> dict[str, date]:
    """Return the most recent shift_date strictly before `as_of` per employee."""
    from sqlalchemy import func

    result = await db.execute(
        select(ScheduleEntry.employee_id, func.max(ScheduleEntry.shift_date))
        .where(ScheduleEntry.shift_date < as_of)
        .group_by(ScheduleEntry.employee_id)
    )
    return {row[0]: row[1] for row in result.all() if row[1] is not None}


async def load_month_schedule_metrics(
    db: AsyncSession,
    target_date: date,
    target_unit_id: str | None = None,
) -> dict[str, MonthScheduleMetrics]:
    """Compute per-employee schedule metrics for the month containing target_date.

    Uses the same shift→hours math as ``app/services/workload.py`` so that the
    rationale's "hours this month" stays in sync with the workload monitor.
    """
    from app.services.shift_utils import SHIFT_DURATION_HOURS, get_shift_date
    from app.services.overtime import (
        BIWEEKLY_SHIFT_OT_THRESHOLD,
        WEEKLY_OT_THRESHOLD_HOURS,
    )

    year = target_date.year
    month = target_date.month
    _, last_day = calendar.monthrange(year, month)
    first = date(year, month, 1)
    last = date(year, month, last_day)
    query_start = first - timedelta(days=first.isocalendar().weekday - 1)
    query_end = last + timedelta(days=7 - last.isocalendar().weekday)

    entries_result = await db.execute(
        select(ScheduleEntry).where(
            ScheduleEntry.shift_date.between(query_start, query_end)
        )
    )
    entries = entries_result.scalars().all()

    # license + home unit lookup
    staff_result = await db.execute(
        select(StaffMaster.employee_id, StaffMaster.license)
    )
    license_map: dict[str, LicenseType] = {
        eid: LicenseType(lic.value) for eid, lic in staff_result.all()
    }
    from app.models.staff import StaffOps

    ops_result = await db.execute(
        select(StaffOps.employee_id, StaffOps.home_unit_id)
    )
    home_unit_map: dict[str, str] = {eid: hu for eid, hu in ops_result.all()}

    # latest cycle anchor for RN biweekly buckets
    hours_result = await db.execute(select(HoursLedger))
    cycle_anchor: dict[str, date] = {}
    for row in hours_result.scalars().all():
        existing = cycle_anchor.get(row.employee_id)
        if not existing or row.cycle_start_date > existing:
            cycle_anchor[row.employee_id] = row.cycle_start_date

    in_month: dict[str, list[ScheduleEntry]] = defaultdict(list)
    full_window: dict[str, list[ScheduleEntry]] = defaultdict(list)
    for entry in entries:
        full_window[entry.employee_id].append(entry)
        if first <= entry.shift_date <= last:
            in_month[entry.employee_id].append(entry)

    day_before = target_date - timedelta(days=1)
    day_after = target_date + timedelta(days=1)

    metrics: dict[str, MonthScheduleMetrics] = {}
    for employee_id, month_entries in in_month.items():
        m = MonthScheduleMetrics()
        m.scheduled_shifts = len(month_entries)
        m.scheduled_hours = round(len(month_entries) * SHIFT_DURATION_HOURS, 2)

        home_unit = home_unit_map.get(employee_id)
        for e in month_entries:
            if home_unit and e.unit_id == home_unit:
                m.home_unit_shifts += 1
            else:
                m.float_shifts += 1

        ot_entries = full_window.get(employee_id, [])
        license = license_map.get(employee_id)
        anchor = cycle_anchor.get(employee_id) or first

        if target_unit_id:
            for e in ot_entries:
                if e.unit_id == target_unit_id and e.shift_date != target_date:
                    m.target_unit_shifts += 1
                if e.shift_date == day_before or e.shift_date == day_after:
                    m.has_adjacent_shift = True

        if license == LicenseType.RN:
            operational_day_counts: dict[date, int] = defaultdict(int)
            biweekly_counts: dict[int, int] = defaultdict(int)
            for e in ot_entries:
                label = (
                    e.shift_label.value if hasattr(e.shift_label, "value") else str(e.shift_label)
                )
                operational_day_counts[get_shift_date(e.shift_date, label)] += 1
                bucket = (e.shift_date - anchor).days // 14
                biweekly_counts[bucket] += 1
            m.double_shift_days = sum(
                1 for c in operational_day_counts.values() if c > 1
            )
            m.peak_biweekly_shifts = max(biweekly_counts.values(), default=0)
            m.projected_overtime_shifts = sum(
                max(0, c - BIWEEKLY_SHIFT_OT_THRESHOLD)
                for c in biweekly_counts.values()
            )
        else:
            weekly_hours: dict[tuple[int, int], float] = defaultdict(float)
            for e in ot_entries:
                iso = e.shift_date.isocalendar()
                weekly_hours[(iso.year, iso.week)] += SHIFT_DURATION_HOURS
            m.peak_week_hours = round(max(weekly_hours.values(), default=0.0), 2)
            m.projected_overtime_hours = round(
                sum(
                    max(0.0, h - WEEKLY_OT_THRESHOLD_HOURS)
                    for h in weekly_hours.values()
                ),
                2,
            )

        metrics[employee_id] = m
    return metrics


async def load_hours_map(db: AsyncSession) -> dict[str, HoursLedger]:
    """Load the most recent hours ledger for each employee."""
    result = await db.execute(select(HoursLedger))
    hours_map: dict[str, HoursLedger] = {}
    for h in result.scalars().all():
        existing = hours_map.get(h.employee_id)
        if not existing or h.cycle_start_date > existing.cycle_start_date:
            hours_map[h.employee_id] = h
    return hours_map
