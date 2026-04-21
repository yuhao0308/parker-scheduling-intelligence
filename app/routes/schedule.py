"""Monthly schedule endpoints: view and auto-generate."""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.db.session import get_db
from app.models.schedule import Callout, ConfirmationStatus, ScheduleEntry
from app.models.staff import StaffMaster
from app.models.unit import Unit
from app.schemas.schedule import (
    AssignedEmployeeOut,
    AutogenSubmitRequest,
    AutogenSubmitResult,
    DayScheduleOut,
    WorkHoursSnapshotOut,
    GenerateScheduleRequest,
    MonthlyScheduleOut,
    RegenerateWeekRequest,
    RegenerateWeekResult,
    ScheduleGenerationResult,
    ShiftSlotOut,
)
from app.services.confirmation import send_week_confirmations
from app.services.scheduler import generate_monthly_schedule, regenerate_week_schedule
from app.services.workload import build_work_hours_snapshot

router = APIRouter(tags=["schedule"])

SHIFT_LABELS = ["DAY", "EVENING", "NIGHT"]


@router.get(
    "/schedule/monthly",
    response_model=MonthlyScheduleOut,
    summary="View the monthly schedule grid",
    description=(
        "Returns every unit/shift slot for the requested month with assignment "
        "status, assigned employees, and callout metadata."
    ),
)
async def get_monthly_schedule(
    year: int = Query(...),
    month: int = Query(...),
    db: AsyncSession = Depends(get_db),
) -> MonthlyScheduleOut:
    """Return the full monthly schedule with slot statuses."""
    _, last_day = calendar.monthrange(year, month)
    first = date(year, month, 1)
    last = date(year, month, last_day)

    # Load all schedule entries for the month, excluding audit-only REPLACED rows
    entries_result = await db.execute(
        select(ScheduleEntry).where(
            ScheduleEntry.shift_date.between(first, last),
            ScheduleEntry.confirmation_status != ConfirmationStatus.REPLACED,
        )
    )
    entries = entries_result.scalars().all()

    # Load all callouts for the month
    callouts_result = await db.execute(
        select(Callout).where(Callout.shift_date.between(first, last))
    )
    callouts = callouts_result.scalars().all()

    # Load all active units
    units_result = await db.execute(select(Unit).where(Unit.is_active == True))
    units = {u.unit_id: u for u in units_result.scalars().all()}

    # Load staff names for display
    staff_ids = {e.employee_id for e in entries}
    staff_map: dict[str, StaffMaster] = {}
    if staff_ids:
        staff_result = await db.execute(
            select(StaffMaster).where(StaffMaster.employee_id.in_(staff_ids))
        )
        staff_map = {s.employee_id: s for s in staff_result.scalars().all()}

    # Group entries: (date, unit_id, shift_label) -> list of employees
    entry_map: dict[tuple[date, str, str], list[AssignedEmployeeOut]] = defaultdict(list)
    for e in entries:
        label = e.shift_label.value if hasattr(e.shift_label, "value") else e.shift_label
        staff = staff_map.get(e.employee_id)
        status_val = (
            e.confirmation_status.value
            if hasattr(e.confirmation_status, "value")
            else str(e.confirmation_status)
        )
        emp_out = AssignedEmployeeOut(
            employee_id=e.employee_id,
            name=staff.name if staff else e.employee_id,
            license=staff.license.value if staff else "UNK",
            entry_id=e.id,
            confirmation_status=status_val,
        )
        entry_map[(e.shift_date, e.unit_id, label)].append(emp_out)

    # Group callouts: (date, unit_id, shift_label) -> count + employee_ids
    callout_map: dict[tuple[date, str, str], int] = defaultdict(int)
    callout_emp_map: dict[tuple[date, str, str], list[str]] = defaultdict(list)
    for c in callouts:
        label = c.shift_label.value if hasattr(c.shift_label, "value") else c.shift_label
        key = (c.shift_date, c.unit_id, label)
        callout_map[key] += 1
        callout_emp_map[key].append(c.employee_id)

    # Build response
    days = []
    for d in range(1, last_day + 1):
        current = date(year, month, d)
        slots = []
        for unit_id, unit in sorted(units.items()):
            for label in SHIFT_LABELS:
                key = (current, unit_id, label)
                assigned = entry_map.get(key, [])
                callout_count = callout_map.get(key, 0)

                if callout_count > 0:
                    status = "callout"
                elif assigned:
                    status = "assigned"
                else:
                    status = "unassigned"

                slots.append(
                    ShiftSlotOut(
                        unit_id=unit_id,
                        unit_name=unit.name,
                        shift_date=current.isoformat(),
                        shift_label=label,
                        status=status,
                        assigned_employees=assigned,
                        callout_count=callout_count,
                        callout_employee_ids=callout_emp_map.get(key, []),
                    )
                )
        days.append(DayScheduleOut(date=current.isoformat(), slots=slots))

    return MonthlyScheduleOut(year=year, month=month, days=days)


@router.post(
    "/schedule/generate",
    response_model=ScheduleGenerationResult,
    summary="Generate a monthly schedule",
    description=(
        "Builds a fresh month of schedule entries using the current filtering and "
        "scoring rules, then reports coverage and unfilled-slot warnings."
    ),
)
async def generate_schedule(
    req: GenerateScheduleRequest,
    db: AsyncSession = Depends(get_db),
) -> ScheduleGenerationResult:
    """Auto-generate a full month's schedule using the scoring engine.

    Pass ``employee_pool`` to restrict assignment to an allowlist
    (supersedes ``staff_count_override``).
    """
    return await generate_monthly_schedule(
        year=req.year,
        month=req.month,
        db=db,
        settings=settings,
        staff_count_override=req.staff_count_override,
        employee_pool=req.employee_pool,
    )


@router.post(
    "/schedule/regenerate-week",
    response_model=RegenerateWeekResult,
    summary="Regenerate the week starting at week_start using an employee pool",
    description=(
        "Re-solves the 7-day window. ACCEPTED (and optionally PENDING) entries "
        "stay frozen; UNSENT/DECLINED/REPLACED slots are dropped and refilled "
        "from the supplied pool allowlist."
    ),
)
async def regenerate_week(
    req: RegenerateWeekRequest,
    db: AsyncSession = Depends(get_db),
) -> RegenerateWeekResult:
    return await regenerate_week_schedule(
        week_start=req.week_start,
        employee_pool=req.employee_pool,
        db=db,
        settings=settings,
        preserve_responded=req.preserve_responded,
    )


@router.post(
    "/schedule/autogen-submit",
    response_model=AutogenSubmitResult,
    summary="Regenerate the week AND immediately send confirmations (supervisor-spec Submit)",
    description=(
        "Compound action wired to the Auto-Gen tab's Submit button: "
        "regenerate-week followed by confirmations/send on the new UNSENT "
        "entries. Atomic from the UI's point of view."
    ),
)
async def autogen_submit(
    req: AutogenSubmitRequest,
    db: AsyncSession = Depends(get_db),
) -> AutogenSubmitResult:
    regen = await regenerate_week_schedule(
        week_start=req.week_start,
        employee_pool=req.employee_pool,
        db=db,
        settings=settings,
        preserve_responded=True,
    )
    sent = await send_week_confirmations(db, req.week_start, unit_ids=None)
    return AutogenSubmitResult(
        week_start=req.week_start,
        entries_generated=regen.entries_created,
        entries_preserved=regen.entries_preserved,
        notifications_sent=sent.notifications_created,
        unfilled_slots=regen.unfilled_slots,
        warnings=regen.warnings,
    )


@router.get(
    "/schedule/work-hours",
    response_model=WorkHoursSnapshotOut,
    summary="Inspect monthly workload and overtime exposure",
    description=(
        "Summarizes scheduled hours, overtime risk, float shifts, and related "
        "workload metrics for the selected month."
    ),
)
async def get_work_hours_snapshot(
    year: int = Query(...),
    month: int = Query(...),
    db: AsyncSession = Depends(get_db),
) -> WorkHoursSnapshotOut:
    """Return a monthly staffing workload snapshot for all active employees."""
    return await build_work_hours_snapshot(db=db, year=year, month=month)
