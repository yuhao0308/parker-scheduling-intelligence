"""Monthly workforce workload snapshot for the shared monitor UI."""

from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.timeclock.kronos_schema import PayCode
from app.integrations.timeclock.source import CSVSource, TimeClockSource
from app.models.hours import HoursLedger
from app.models.schedule import Callout, ScheduleEntry
from app.models.staff import StaffMaster, StaffOps
from app.schemas.common import EmploymentClass, LicenseType
from app.schemas.schedule import (
    EmployeeWorkHoursOut,
    WorkHoursSnapshotOut,
    WorkHoursSummaryOut,
    WorkloadPeriodOut,
)
from app.services.overtime import (
    BIWEEKLY_SHIFT_OT_THRESHOLD,
    HIGH_OT_SOFT_CAP_HOURS,
    WEEKLY_OT_THRESHOLD_HOURS,
    cycle_budget_hours,
)
from app.services.shift_utils import SHIFT_DURATION_HOURS, get_shift_date

BIWEEKLY_CYCLE_DAYS = 14

# Known Monday biweekly anchor — same value the time-clock generator uses
# (see app/integrations/timeclock/generator.py::_biweekly_cycle_start). All
# cycles in the system are 14-day windows offset from this date, so cycle
# boundaries align across schedule, time-clock, and ledger tables.
BIWEEKLY_CYCLE_ANCHOR = date(2026, 3, 30)
PRODUCTIVE_PAY_CODES = {PayCode.REG, PayCode.OT, PayCode.DT, PayCode.HOL}


def _view_cycle_start(year: int, month: int) -> date:
    """Return the biweekly cycle anchor that overlaps with the view month.

    Picks the cycle containing the first of the requested month — that's the
    cycle the workload bar should reflect. Without this, a May view would
    keep showing the latest historical cycle (April-anchored) and miss any
    schedule entries the user just arranged for May.
    """
    first = date(year, month, 1)
    delta_days = (first - BIWEEKLY_CYCLE_ANCHOR).days
    if delta_days >= 0:
        offset = (delta_days // BIWEEKLY_CYCLE_DAYS) * BIWEEKLY_CYCLE_DAYS
    else:
        # View is before the anchor — round backward so we still land on a
        # 14-day boundary. (e.g., viewing 2026-01-15 lands on 2026-01-19's
        # predecessor, 2026-01-05.)
        offset = -(
            ((-delta_days + BIWEEKLY_CYCLE_DAYS - 1) // BIWEEKLY_CYCLE_DAYS)
            * BIWEEKLY_CYCLE_DAYS
        )
    return BIWEEKLY_CYCLE_ANCHOR + timedelta(days=offset)


def _biweekly_cycle_start_for_date(value: date) -> date:
    delta_days = (value - BIWEEKLY_CYCLE_ANCHOR).days
    if delta_days >= 0:
        offset = (delta_days // BIWEEKLY_CYCLE_DAYS) * BIWEEKLY_CYCLE_DAYS
    else:
        offset = -(
            ((-delta_days + BIWEEKLY_CYCLE_DAYS - 1) // BIWEEKLY_CYCLE_DAYS)
            * BIWEEKLY_CYCLE_DAYS
        )
    return BIWEEKLY_CYCLE_ANCHOR + timedelta(days=offset)


def _week_periods_for_month(first: date, last: date) -> list[tuple[date, date]]:
    start = first - timedelta(days=first.isocalendar().weekday - 1)
    end = last + timedelta(days=7 - last.isocalendar().weekday)
    periods: list[tuple[date, date]] = []
    current = start
    while current <= end:
        periods.append((current, current + timedelta(days=6)))
        current += timedelta(days=7)
    return periods


def _biweekly_periods_for_month(first: date, last: date) -> list[tuple[date, date]]:
    periods: list[tuple[date, date]] = []
    current = _biweekly_cycle_start_for_date(first)
    while current <= last:
        periods.append((current, current + timedelta(days=BIWEEKLY_CYCLE_DAYS - 1)))
        current += timedelta(days=BIWEEKLY_CYCLE_DAYS)
    return periods


def _worked_hours_by_employee_from_daily_totals(totals) -> dict[str, tuple[float, int]]:
    """Aggregate daily actuals into per-employee worked hours and shifts.

    Kronos daily totals may split one worked shift into multiple pay-code or
    cost-center rows. Hours should sum across productive pay codes, while
    shifts should only count rows that carry the shift_count.
    """
    out: dict[str, tuple[float, int]] = defaultdict(lambda: (0.0, 0))
    for total in totals:
        if total.pay_code not in PRODUCTIVE_PAY_CODES:
            continue
        hours, shifts = out[total.person_number]
        out[total.person_number] = (
            hours + total.hours,
            shifts + total.shift_count,
        )
    return {
        employee_id: (round(hours, 2), shifts)
        for employee_id, (hours, shifts) in out.items()
    }


def _worked_hours_by_employee_day(totals) -> dict[tuple[str, date], tuple[float, int]]:
    out: dict[tuple[str, date], tuple[float, int]] = defaultdict(lambda: (0.0, 0))
    for total in totals:
        if total.pay_code not in PRODUCTIVE_PAY_CODES:
            continue
        key = (total.person_number, total.work_date)
        hours, shifts = out[key]
        out[key] = (hours + total.hours, shifts + total.shift_count)
    return {key: (round(hours, 2), shifts) for key, (hours, shifts) in out.items()}


async def _load_monthly_actuals(
    source: TimeClockSource,
    first: date,
    last: date,
    as_of: date,
) -> dict[str, tuple[float, int]]:
    """Return actual worked time inside the viewed month, clipped to as_of."""
    if first > as_of:
        return {}

    actuals_end = min(last, as_of)
    try:
        totals = await source.fetch_daily_totals(first, actuals_end)
    except FileNotFoundError:
        # Demo environments can run without generated time-clock artifacts.
        # In that case the biweekly HoursLedger still powers OT projection,
        # while month actuals safely read as zero.
        return {}
    return _worked_hours_by_employee_from_daily_totals(totals)


async def _load_period_actuals(
    source: TimeClockSource,
    start: date,
    end: date,
    as_of: date,
) -> dict[tuple[str, date], tuple[float, int]]:
    if start > as_of:
        return {}

    actuals_end = min(end, as_of)
    try:
        totals = await source.fetch_daily_totals(start, actuals_end)
    except FileNotFoundError:
        return {}
    return _worked_hours_by_employee_day(totals)


def _sum_period_actuals(
    actuals_by_day: dict[tuple[str, date], tuple[float, int]],
    employee_id: str,
    start: date,
    end: date,
) -> tuple[float, int]:
    hours = 0.0
    shifts = 0
    current = start
    while current <= end:
        day_hours, day_shifts = actuals_by_day.get((employee_id, current), (0.0, 0))
        hours += day_hours
        shifts += day_shifts
        current += timedelta(days=1)
    return round(hours, 2), shifts


@dataclass
class EmployeeMetrics:
    scheduled_hours: float = 0.0
    scheduled_shifts: int = 0
    peak_week_hours: float = 0.0
    projected_overtime_hours: float = 0.0
    peak_biweekly_shifts: int = 0
    projected_overtime_shifts: int = 0
    double_shift_days: int = 0
    home_unit_shifts: int = 0
    float_shifts: int = 0
    callout_count: int = 0
    primary_unit_id: str | None = None
    scheduled_unit_ids: list[str] = field(default_factory=list)
    overtime_status: str = "healthy"
    overtime_detail: str = "No OT pressure in this month."


def summarize_standard_schedule(
    shift_dates: list[date],
) -> tuple[float, float]:
    """Return peak weekly hours and OT hours for non-RN staff."""
    weekly_hours: dict[tuple[int, int], float] = defaultdict(float)
    for shift_date in shift_dates:
        iso = shift_date.isocalendar()
        weekly_hours[(iso.year, iso.week)] += SHIFT_DURATION_HOURS

    peak_week_hours = max(weekly_hours.values(), default=0.0)
    overtime_hours = sum(
        max(0.0, hours - WEEKLY_OT_THRESHOLD_HOURS)
        for hours in weekly_hours.values()
    )
    return peak_week_hours, overtime_hours


def summarize_rn_schedule(
    employee_shifts: list[tuple[date, str]],
    cycle_anchor: date,
) -> tuple[int, int, int]:
    """Return daily double-shift days plus peak/excess biweekly shifts for RNs."""
    operational_day_counts: dict[date, int] = defaultdict(int)
    biweekly_counts: dict[int, int] = defaultdict(int)

    for shift_date, shift_label in employee_shifts:
        operational_day_counts[get_shift_date(shift_date, shift_label)] += 1
        biweekly_bucket = (shift_date - cycle_anchor).days // 14
        biweekly_counts[biweekly_bucket] += 1

    double_shift_days = sum(1 for count in operational_day_counts.values() if count > 1)
    peak_biweekly_shifts = max(biweekly_counts.values(), default=0)
    overtime_shifts = sum(
        max(0, count - BIWEEKLY_SHIFT_OT_THRESHOLD)
        for count in biweekly_counts.values()
    )
    return double_shift_days, peak_biweekly_shifts, overtime_shifts


def standard_overtime_status(
    peak_week_hours: float,
    overtime_hours: float,
) -> tuple[str, str]:
    if peak_week_hours > HIGH_OT_SOFT_CAP_HOURS:
        return "high_ot", "Peak week is beyond the soft OT cap."
    if overtime_hours > 0:
        return "overtime", f"{overtime_hours:.1f} OT hours projected in this month."
    if peak_week_hours >= WEEKLY_OT_THRESHOLD_HOURS - SHIFT_DURATION_HOURS:
        return "near_ot", "Within one shift of weekly OT."
    return "healthy", "No OT pressure in this month."


def rn_overtime_status(
    double_shift_days: int,
    peak_biweekly_shifts: int,
    overtime_shifts: int,
) -> tuple[str, str]:
    if overtime_shifts > 0 or double_shift_days > 1:
        detail = []
        if overtime_shifts > 0:
            detail.append(f"{overtime_shifts} biweekly OT shift")
        if double_shift_days > 0:
            detail.append(f"{double_shift_days} double-shift day")
        return "high_ot", ", ".join(detail) + "."
    if double_shift_days > 0:
        return "overtime", "Daily OT is projected in this month."
    if peak_biweekly_shifts >= BIWEEKLY_SHIFT_OT_THRESHOLD - 1:
        return "near_ot", "Within one shift of the RN biweekly OT limit."
    return "healthy", "No OT pressure in this month."


async def build_work_hours_snapshot(
    db: AsyncSession,
    year: int,
    month: int,
    *,
    timeclock_source: TimeClockSource | None = None,
    as_of: date | None = None,
) -> WorkHoursSnapshotOut:
    _, last_day = calendar.monthrange(year, month)
    first = date(year, month, 1)
    last = date(year, month, last_day)

    # Expand to complete ISO weeks so boundary-week OT is not underestimated
    query_start = first - timedelta(days=first.isocalendar().weekday - 1)
    query_end = last + timedelta(days=7 - last.isocalendar().weekday)

    staff_result = await db.execute(
        select(StaffMaster, StaffOps)
        .outerjoin(StaffOps, StaffMaster.employee_id == StaffOps.employee_id)
        .where(StaffMaster.is_active == True)
        .order_by(StaffMaster.name)
    )
    staff_rows = staff_result.all()

    entries_result = await db.execute(
        select(ScheduleEntry).where(ScheduleEntry.shift_date.between(query_start, query_end))
    )
    entries = entries_result.scalars().all()

    callouts_result = await db.execute(
        select(Callout).where(Callout.shift_date.between(first, last))
    )
    callouts = callouts_result.scalars().all()

    # The view cycle drives the workload bar — pick the biweekly window that
    # overlaps with the first of the requested month so the bar reflects the
    # schedule the user is actually looking at.
    view_cycle_start = _view_cycle_start(year, month)
    weekly_period_ranges = _week_periods_for_month(first, last)
    biweekly_period_ranges = _biweekly_periods_for_month(first, last)

    today = as_of or date.today()
    source = timeclock_source or CSVSource()
    monthly_actuals = await _load_monthly_actuals(
        source=source,
        first=first,
        last=last,
        as_of=today,
    )
    period_actuals = await _load_period_actuals(
        source=source,
        start=query_start,
        end=query_end,
        as_of=today,
    )

    hours_result = await db.execute(select(HoursLedger))
    latest_hours: dict[str, HoursLedger] = {}
    view_cycle_hours: dict[str, HoursLedger] = {}
    cycle_hours_by_employee: dict[tuple[str, date], HoursLedger] = {}
    for row in hours_result.scalars().all():
        existing = latest_hours.get(row.employee_id)
        if not existing or row.cycle_start_date > existing.cycle_start_date:
            latest_hours[row.employee_id] = row
        if row.cycle_start_date == view_cycle_start:
            view_cycle_hours[row.employee_id] = row
        cycle_hours_by_employee[(row.employee_id, row.cycle_start_date)] = row

    entry_map: dict[str, list[ScheduleEntry]] = defaultdict(list)
    ot_entry_map: dict[str, list[ScheduleEntry]] = defaultdict(list)
    for entry in entries:
        ot_entry_map[entry.employee_id].append(entry)
        if first <= entry.shift_date <= last:
            entry_map[entry.employee_id].append(entry)

    callout_counts: dict[str, int] = defaultdict(int)
    for callout in callouts:
        callout_counts[callout.employee_id] += 1

    employees: list[EmployeeWorkHoursOut] = []
    near_ot = 0
    in_ot = 0
    high_ot = 0
    daily_ot_count = 0
    biweekly_ot_count = 0
    total_scheduled_hours = 0.0
    total_float_shifts = 0

    for staff, ops in staff_rows:
        employee_entries = entry_map.get(staff.employee_id, [])
        ot_entries = ot_entry_map.get(staff.employee_id, [])
        unit_counter: Counter[str] = Counter()
        home_unit_shifts = 0
        float_shifts = 0

        for entry in employee_entries:
            unit_counter[entry.unit_id] += 1
            if not ops:
                continue
            if entry.unit_id == ops.home_unit_id:
                home_unit_shifts += 1
            else:
                float_shifts += 1

        scheduled_hours = round(len(employee_entries) * SHIFT_DURATION_HOURS, 2)
        scheduled_shifts = len(employee_entries)
        total_scheduled_hours += scheduled_hours
        total_float_shifts += float_shifts

        current_hours = latest_hours.get(staff.employee_id)
        primary_unit_id = unit_counter.most_common(1)[0][0] if unit_counter else None

        # ---- Biweekly-cycle workload bar inputs ----
        # The bar shows worked (Kronos-derived) + scheduled-but-not-yet-worked
        # + remaining budget. We compute scheduled-remaining as
        # (total_cycle_hours - worked_cycle_hours), clamped at zero, so an
        # employee whose worked hours already exceed their schedule (a common
        # demo case for the doubles employee) doesn't double-count.
        cycle_hours_row = view_cycle_hours.get(staff.employee_id)
        worked_hours_this_cycle = (
            round(cycle_hours_row.hours_this_cycle, 2)
            if cycle_hours_row
            else 0.0
        )
        cycle_start = view_cycle_start
        cycle_end = cycle_start + timedelta(days=BIWEEKLY_CYCLE_DAYS - 1)
        worked_hours_this_month, worked_shifts_this_month = monthly_actuals.get(
            staff.employee_id,
            (0.0, 0),
        )
        try:
            employment_class_enum = EmploymentClass(staff.employment_class.value)
        except ValueError:
            employment_class_enum = EmploymentClass.FT
        budget_hours_this_cycle = cycle_budget_hours(employment_class_enum)

        weekly_periods: list[WorkloadPeriodOut] = []
        for period_start, period_end in weekly_period_ranges:
            worked_hours, worked_shifts = _sum_period_actuals(
                period_actuals,
                staff.employee_id,
                period_start,
                period_end,
            )
            period_entries = [
                e for e in ot_entries if period_start <= e.shift_date <= period_end
            ]
            period_scheduled_hours = round(len(period_entries) * SHIFT_DURATION_HOURS, 2)
            scheduled_remaining = round(
                max(0.0, period_scheduled_hours - worked_hours),
                2,
            )
            projected_hours = round(worked_hours + scheduled_remaining, 2)
            weekly_periods.append(
                WorkloadPeriodOut(
                    period_type="week",
                    start_date=period_start,
                    end_date=period_end,
                    worked_hours=worked_hours,
                    worked_shifts=worked_shifts,
                    scheduled_hours=scheduled_remaining,
                    scheduled_shifts=max(0, len(period_entries) - worked_shifts),
                    projected_hours=projected_hours,
                    projected_shifts=max(len(period_entries), worked_shifts),
                    threshold_hours=WEEKLY_OT_THRESHOLD_HOURS,
                    remaining_hours=round(
                        max(0.0, WEEKLY_OT_THRESHOLD_HOURS - projected_hours),
                        2,
                    ),
                    overtime_hours=round(
                        max(0.0, projected_hours - WEEKLY_OT_THRESHOLD_HOURS),
                        2,
                    ),
                )
            )

        biweekly_periods: list[WorkloadPeriodOut] = []
        for period_start, period_end in biweekly_period_ranges:
            period_hours_row = cycle_hours_by_employee.get(
                (staff.employee_id, period_start)
            )
            worked_hours = (
                round(period_hours_row.hours_this_cycle, 2)
                if period_hours_row
                else 0.0
            )
            worked_shifts = (
                period_hours_row.shift_count_this_biweek
                if period_hours_row
                else 0
            )
            period_entries = [
                e for e in ot_entries if period_start <= e.shift_date <= period_end
            ]
            period_scheduled_hours = round(len(period_entries) * SHIFT_DURATION_HOURS, 2)
            scheduled_remaining = round(
                max(0.0, period_scheduled_hours - worked_hours),
                2,
            )
            projected_hours = round(worked_hours + scheduled_remaining, 2)
            operational_days: dict[date, int] = defaultdict(int)
            for entry in period_entries:
                label = (
                    entry.shift_label.value
                    if hasattr(entry.shift_label, "value")
                    else str(entry.shift_label)
                )
                operational_days[get_shift_date(entry.shift_date, label)] += 1
            double_shift_count = sum(1 for count in operational_days.values() if count > 1)
            threshold_hours = (
                BIWEEKLY_SHIFT_OT_THRESHOLD * SHIFT_DURATION_HOURS
                if staff.license == LicenseType.RN
                else budget_hours_this_cycle
            )
            biweekly_periods.append(
                WorkloadPeriodOut(
                    period_type="biweekly",
                    start_date=period_start,
                    end_date=period_end,
                    worked_hours=worked_hours,
                    worked_shifts=worked_shifts,
                    scheduled_hours=scheduled_remaining,
                    scheduled_shifts=max(0, len(period_entries) - worked_shifts),
                    projected_hours=projected_hours,
                    projected_shifts=max(len(period_entries), worked_shifts),
                    threshold_hours=threshold_hours,
                    remaining_hours=round(
                        max(0.0, threshold_hours - projected_hours),
                        2,
                    ),
                    overtime_hours=round(
                        max(0.0, projected_hours - threshold_hours),
                        2,
                    ),
                    double_shift_days=double_shift_count,
                )
            )

        if staff.license == LicenseType.RN:
            peak_week_hours = 0.0
            projected_overtime_hours = 0.0
            double_shift_days = sum(period.double_shift_days for period in biweekly_periods)
            peak_biweekly_shifts = max(
                (period.projected_shifts for period in biweekly_periods),
                default=0,
            )
            projected_overtime_shifts = sum(
                max(0, period.projected_shifts - BIWEEKLY_SHIFT_OT_THRESHOLD)
                for period in biweekly_periods
            )
            overtime_status, overtime_detail = rn_overtime_status(
                double_shift_days,
                peak_biweekly_shifts,
                projected_overtime_shifts,
            )
        else:
            peak_week_hours = max(
                (period.projected_hours for period in weekly_periods),
                default=0.0,
            )
            projected_overtime_hours = round(
                sum(period.overtime_hours for period in weekly_periods),
                2,
            )
            peak_biweekly_shifts = 0
            projected_overtime_shifts = 0
            double_shift_days = 0
            overtime_status, overtime_detail = standard_overtime_status(
                peak_week_hours,
                projected_overtime_hours,
            )

        if overtime_status == "near_ot":
            near_ot += 1
        elif overtime_status == "overtime":
            in_ot += 1
        elif overtime_status == "high_ot":
            high_ot += 1

        cycle_entries = [
            e for e in ot_entries if cycle_start <= e.shift_date <= cycle_end
        ]
        total_cycle_scheduled_hours = round(
            len(cycle_entries) * SHIFT_DURATION_HOURS, 2
        )
        scheduled_hours_this_cycle = round(
            max(0.0, total_cycle_scheduled_hours - worked_hours_this_cycle), 2
        )

        # Aggregate OT counts for the summary band. Daily OT is RN-specific —
        # a second shift inside the same operational day. Biweekly OT follows
        # the RN shift rule and non-RN cycle budgets.
        if (
            staff.license == LicenseType.RN
            and any(period.double_shift_days > 0 for period in biweekly_periods)
        ):
            daily_ot_count += 1
        if staff.license == LicenseType.RN:
            has_biweekly_ot = any(
                period.projected_shifts > BIWEEKLY_SHIFT_OT_THRESHOLD
                for period in biweekly_periods
            )
        else:
            has_biweekly_ot = any(period.overtime_hours > 0 for period in biweekly_periods)
        if has_biweekly_ot:
            biweekly_ot_count += 1

        employees.append(
            EmployeeWorkHoursOut(
                employee_id=staff.employee_id,
                name=staff.name,
                license=staff.license.value,
                employment_class=staff.employment_class.value,
                home_unit_id=ops.home_unit_id if ops else None,
                current_cycle_hours=round(current_hours.hours_this_cycle, 2) if current_hours else 0.0,
                current_cycle_shifts=current_hours.shift_count_this_biweek if current_hours else 0,
                scheduled_hours=scheduled_hours,
                scheduled_shifts=scheduled_shifts,
                worked_hours_this_month=worked_hours_this_month,
                worked_shifts_this_month=worked_shifts_this_month,
                peak_week_hours=round(peak_week_hours, 2),
                projected_overtime_hours=round(projected_overtime_hours, 2),
                peak_biweekly_shifts=peak_biweekly_shifts,
                projected_overtime_shifts=projected_overtime_shifts,
                double_shift_days=double_shift_days,
                home_unit_shifts=home_unit_shifts,
                float_shifts=float_shifts,
                callout_count=callout_counts.get(staff.employee_id, 0),
                primary_unit_id=primary_unit_id,
                scheduled_unit_ids=sorted(unit_counter.keys()),
                overtime_status=overtime_status,
                overtime_detail=overtime_detail,
                worked_hours_this_cycle=worked_hours_this_cycle,
                scheduled_hours_this_cycle=scheduled_hours_this_cycle,
                budget_hours_this_cycle=budget_hours_this_cycle,
                cycle_start_date=cycle_start,
                cycle_end_date=cycle_end,
                weekly_periods=weekly_periods,
                biweekly_periods=biweekly_periods,
            )
        )

    employees.sort(
        key=lambda employee: (
            {"high_ot": 0, "overtime": 1, "near_ot": 2, "healthy": 3}[employee.overtime_status],
            -employee.scheduled_hours,
            employee.name,
        )
    )

    employee_count = len(employees)
    summary = WorkHoursSummaryOut(
        employee_count=employee_count,
        total_scheduled_hours=round(total_scheduled_hours, 2),
        average_scheduled_hours=round(total_scheduled_hours / employee_count, 2) if employee_count else 0.0,
        employees_near_ot=near_ot,
        employees_in_ot=in_ot,
        employees_high_ot=high_ot,
        total_float_shifts=total_float_shifts,
        daily_ot_count=daily_ot_count,
        biweekly_ot_count=biweekly_ot_count,
    )
    return WorkHoursSnapshotOut(year=year, month=month, summary=summary, employees=employees)
