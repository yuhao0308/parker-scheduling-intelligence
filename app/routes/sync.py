from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.schedule import HoursSyncPayload, ScheduleSyncPayload
from app.schemas.staff import StaffSyncPayload, SyncResult
from app.services.data_sync import (
    sync_callouts,
    sync_hours,
    sync_pto,
    sync_schedule_entries,
    sync_staff,
)

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/staff", response_model=SyncResult)
async def sync_staff_endpoint(
    payload: StaffSyncPayload,
    db: AsyncSession = Depends(get_db),
) -> SyncResult:
    return await sync_staff(payload.records, db)


@router.post("/schedule")
async def sync_schedule_endpoint(
    payload: ScheduleSyncPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:
    entries = await sync_schedule_entries(payload.schedule_entries, db) if payload.schedule_entries else 0
    callouts = await sync_callouts(payload.callouts, db) if payload.callouts else 0
    pto = await sync_pto(payload.pto_entries, db) if payload.pto_entries else 0
    return {"schedule_entries": entries, "callouts": callouts, "pto_entries": pto}


@router.post("/hours", response_model=SyncResult)
async def sync_hours_endpoint(
    payload: HoursSyncPayload,
    db: AsyncSession = Depends(get_db),
) -> SyncResult:
    return await sync_hours(payload.records, db)
