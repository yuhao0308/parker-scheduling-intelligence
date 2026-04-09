"""SmartLinx data ingestion service.

Handles bulk upsert of staff, schedule, and hours data.
Uses PostgreSQL INSERT ... ON CONFLICT ... DO UPDATE for idempotent sync.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hours import HoursLedger
from app.models.schedule import Callout, PTOEntry, ScheduleEntry
from app.models.staff import StaffCrossTraining, StaffMaster, StaffOps
from app.models.unit import Unit
from app.schemas.schedule import (
    CalloutSyncRecord,
    HoursLedgerSyncRecord,
    PTOSyncRecord,
    ScheduleEntrySyncRecord,
)
from app.schemas.staff import StaffSyncRecord, SyncResult


async def sync_staff(
    records: list[StaffSyncRecord], db: AsyncSession
) -> SyncResult:
    """Upsert staff master, ops, and cross-training records."""
    created = 0
    updated = 0

    for rec in records:
        existing = await db.get(StaffMaster, rec.employee_id)
        if existing:
            existing.name = rec.name
            existing.license = rec.license
            existing.employment_class = rec.employment_class
            existing.zip_code = rec.zip_code
            existing.is_active = rec.is_active
            updated += 1
        else:
            staff = StaffMaster(
                employee_id=rec.employee_id,
                name=rec.name,
                license=rec.license,
                employment_class=rec.employment_class,
                zip_code=rec.zip_code,
                is_active=rec.is_active,
            )
            db.add(staff)
            created += 1

        # Upsert staff ops
        existing_ops = await db.get(StaffOps, rec.employee_id)
        if existing_ops:
            existing_ops.home_unit_id = rec.home_unit_id
            existing_ops.hire_date = rec.hire_date
        else:
            ops = StaffOps(
                employee_id=rec.employee_id,
                home_unit_id=rec.home_unit_id,
                hire_date=rec.hire_date,
            )
            db.add(ops)

        # Replace cross-training records
        result = await db.execute(
            select(StaffCrossTraining).where(
                StaffCrossTraining.employee_id == rec.employee_id
            )
        )
        for ct in result.scalars().all():
            await db.delete(ct)

        for unit_id in rec.cross_trained_units:
            db.add(
                StaffCrossTraining(
                    employee_id=rec.employee_id,
                    unit_id=unit_id,
                )
            )

    await db.commit()
    return SyncResult(created=created, updated=updated, total=len(records))


async def sync_schedule_entries(
    records: list[ScheduleEntrySyncRecord], db: AsyncSession
) -> int:
    """Bulk insert schedule entries (replaces existing for the date range)."""
    for rec in records:
        entry = ScheduleEntry(
            employee_id=rec.employee_id,
            unit_id=rec.unit_id,
            shift_date=rec.shift_date,
            shift_label=rec.shift_label,
            is_published=rec.is_published,
            is_clocked_in=rec.is_clocked_in,
        )
        db.add(entry)
    await db.commit()
    return len(records)


async def sync_callouts(records: list[CalloutSyncRecord], db: AsyncSession) -> int:
    """Bulk insert callout records."""
    for rec in records:
        callout = Callout(
            employee_id=rec.employee_id,
            unit_id=rec.unit_id,
            shift_date=rec.shift_date,
            shift_label=rec.shift_label,
            reason=rec.reason,
            reported_at=rec.reported_at,
        )
        db.add(callout)
    await db.commit()
    return len(records)


async def sync_pto(records: list[PTOSyncRecord], db: AsyncSession) -> int:
    """Bulk insert PTO entries."""
    for rec in records:
        pto = PTOEntry(
            employee_id=rec.employee_id,
            start_date=rec.start_date,
            end_date=rec.end_date,
        )
        db.add(pto)
    await db.commit()
    return len(records)


async def sync_hours(
    records: list[HoursLedgerSyncRecord], db: AsyncSession
) -> SyncResult:
    """Upsert hours ledger records."""
    created = 0
    updated = 0
    now = datetime.now(timezone.utc)

    for rec in records:
        result = await db.execute(
            select(HoursLedger).where(
                HoursLedger.employee_id == rec.employee_id,
                HoursLedger.cycle_start_date == rec.cycle_start_date,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.hours_this_cycle = rec.hours_this_cycle
            existing.shift_count_this_biweek = rec.shift_count_this_biweek
            existing.updated_at = now
            updated += 1
        else:
            ledger = HoursLedger(
                employee_id=rec.employee_id,
                cycle_start_date=rec.cycle_start_date,
                hours_this_cycle=rec.hours_this_cycle,
                shift_count_this_biweek=rec.shift_count_this_biweek,
                updated_at=now,
            )
            db.add(ledger)
            created += 1

    await db.commit()
    return SyncResult(created=created, updated=updated, total=len(records))
