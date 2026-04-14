"""Monthly workforce workload snapshot for the shared monitor UI."""

from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hours import HoursLedger
from app.models.schedule import Callout, ScheduleEntry
from app.models.staff import StaffMaster, StaffOps
from app.schemas.common import LicenseType
from app.schemas.schedule import (
    EmployeeWorkHoursOut,
    WorkHoursSnapshotOut,
    WorkHoursSummaryOut,
)
from app.services.overtime import (
    BIWEEKLY_SHIFT_OT_THRESHOLD,
    HIGH_OT_SOFT_CAP_HOURS,
    WEEKLY_OT_THRESHOLD_HOURS,
)
from app.services.shift_utils import SHIFT_DURATION_HOURS, get_shift_date


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
    if double_shift_days > 0 or peak_biweekly_shifts > BIWEEKLY_SHIFT_OT_THRESHOLD:
        return "overtime", "Daily or biweekly OT is projected in this month."
    if peak_biweekly_shifts >= BIWEEKLY_SHIFT_OT_THRESHOLD - 1:
        return "near_ot", "Within one shift of the RN biweekly OT limit."
    return "healthy", "No OT pressure in this month."


async def build_work_hours_snapshot(
    db: AsyncSession,
    year: int,
    month: int,
) -> WorkHoursSnapshotOut:
    _, last_day = calendar.monthrange(year, month)
    first = date(year, month, 1)
    last = date(year, month, last_day)

    staff_result = await db.execute(
        select(StaffMaster, StaffOps)
        .outerjoin(StaffOps, StaffMaster.employee_id == StaffOps.employee_id)
        .where(StaffMaster.is_active == True)
        .order_by(StaffMaster.name)
    )
    staff_rows = staff_result.all()

    entries_result = await db.execute(
        select(ScheduleEntry).where(ScheduleEntry.shift_date.between(first, last))
    )
    entries = entries_result.scalars().all()

    callouts_result = await db.execute(
        select(Callout).where(Callout.shift_date.between(first, last))
    )
    callouts = callouts_result.scalars().all()

    hours_result = await db.execute(select(HoursLedger))
    latest_hours: dict[str, HoursLedger] = {}
    for row in hours_result.scalars().all():
        existing = latest_hours.get(row.employee_id)
        if not existing or row.cycle_start_date > existing.cycle_start_date:
            latest_hours[row.employee_id] = row

    entry_map: dict[str, list[ScheduleEntry]] = defaultdict(list)
    for entry in entries:
        entry_map[entry.employee_id].append(entry)

    callout_counts: dict[str, int] = defaultdict(int)
    for callout in callouts:
        callout_counts[callout.employee_id] += 1

    employees: list[EmployeeWorkHoursOut] = []
    near_ot = 0
    in_ot = 0
    high_ot = 0
    total_scheduled_hours = 0.0
    total_float_shifts = 0

    for staff, ops in staff_rows:
        employee_entries = entry_map.get(staff.employee_id, [])
        unit_counter: Counter[str] = Counter()
        shift_dates: list[date] = []
        rn_shifts: list[tuple[date, str]] = []
        home_unit_shifts = 0
        float_shifts = 0

        for entry in employee_entries:
            shift_dates.append(entry.shift_date)
            label = entry.shift_label.value if hasattr(entry.shift_label, "value") else str(entry.shift_label)
            rn_shifts.append((entry.shift_date, label))
            unit_counter[entry.unit_id] += 1
            if ops and entry.unit_id == ops.home_unit_id:
                home_unit_shifts += 1
            else:
                float_shifts += 1

        scheduled_hours = round(len(employee_entries) * SHIFT_DURATION_HOURS, 2)
        scheduled_shifts = len(employee_entries)
        total_scheduled_hours += scheduled_hours
        total_float_shifts += float_shifts

        peak_week_hours = 0.0
        projected_overtime_hours = 0.0
        peak_biweekly_shifts = 0
        projected_overtime_shifts = 0
        double_shift_days = 0

        cycle_anchor = latest_hours.get(staff.employee_id, None)
        anchor_date = cycle_anchor.cycle_start_date if cycle_anchor else first

        if staff.license == LicenseType.RN:
            double_shift_days, peak_biweekly_shifts, projected_overtime_shifts = summarize_rn_schedule(
                rn_shifts,
                anchor_date,
            )
            overtime_status, overtime_detail = rn_overtime_status(
                double_shift_days,
                peak_biweekly_shifts,
                projected_overtime_shifts,
            )
        else:
            peak_week_hours, projected_overtime_hours = summarize_standard_schedule(shift_dates)
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

        current_hours = latest_hours.get(staff.employee_id)
        primary_unit_id = unit_counter.most_common(1)[0][0] if unit_counter else None

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
    )
    return WorkHoursSnapshotOut(year=year, month=month, summary=summary, employees=employees)
