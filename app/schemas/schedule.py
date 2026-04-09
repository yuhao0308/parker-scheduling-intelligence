from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.common import ShiftLabel


class ScheduleEntrySyncRecord(BaseModel):
    employee_id: str
    unit_id: str
    shift_date: date
    shift_label: ShiftLabel
    is_published: bool = True
    is_clocked_in: Optional[bool] = None


class CalloutSyncRecord(BaseModel):
    employee_id: str
    unit_id: str
    shift_date: date
    shift_label: ShiftLabel
    reason: Optional[str] = None
    reported_at: datetime


class PTOSyncRecord(BaseModel):
    employee_id: str
    start_date: date
    end_date: date


class ScheduleSyncPayload(BaseModel):
    schedule_entries: List[ScheduleEntrySyncRecord] = []
    callouts: List[CalloutSyncRecord] = []
    pto_entries: List[PTOSyncRecord] = []


class HoursLedgerSyncRecord(BaseModel):
    employee_id: str
    cycle_start_date: date
    hours_this_cycle: float
    shift_count_this_biweek: int = 0


class HoursSyncPayload(BaseModel):
    records: List[HoursLedgerSyncRecord]
