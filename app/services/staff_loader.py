"""Shared DB helpers for loading staff, schedule context, and hours data.

Extracted from recommendation.py so that both the recommendation pipeline
and the monthly scheduler can reuse the same data-loading logic.
"""

from __future__ import annotations

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

    result = await db.execute(
        select(ScheduleEntry).where(
            ScheduleEntry.shift_date.between(date_range_start, date_range_end)
        )
    )
    entries = result.scalars().all()

    employee_shifts: dict[str, list[tuple[date, ShiftLabel]]] = {}
    employees_scheduled: set[str] = set()

    for e in entries:
        employee_shifts.setdefault(e.employee_id, []).append(
            (e.shift_date, ShiftLabel(e.shift_label.value))
        )
        if e.shift_date == target_date and e.shift_label.value == target_label.value:
            employees_scheduled.add(e.employee_id)

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
    )


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


async def load_hours_map(db: AsyncSession) -> dict[str, HoursLedger]:
    """Load the most recent hours ledger for each employee."""
    result = await db.execute(select(HoursLedger))
    hours_map: dict[str, HoursLedger] = {}
    for h in result.scalars().all():
        existing = hours_map.get(h.employee_id)
        if not existing or h.cycle_start_date > existing.cycle_start_date:
            hours_map[h.employee_id] = h
    return hours_map
