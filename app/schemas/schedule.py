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


# --- Monthly schedule view schemas ---


class AssignedEmployeeOut(BaseModel):
    employee_id: str
    name: str
    license: str


class ShiftSlotOut(BaseModel):
    unit_id: str
    unit_name: str
    shift_date: str
    shift_label: str
    status: str  # "assigned" | "unassigned" | "callout"
    assigned_employees: List[AssignedEmployeeOut]
    callout_count: int
    callout_employee_ids: List[str] = []


class DayScheduleOut(BaseModel):
    date: str
    slots: List[ShiftSlotOut]


class MonthlyScheduleOut(BaseModel):
    year: int
    month: int
    days: List[DayScheduleOut]


class GenerateScheduleRequest(BaseModel):
    year: int
    month: int
    staff_count_override: Optional[int] = None


class ScheduleGenerationResult(BaseModel):
    entries_created: int
    warnings: List[str]
    scenario: str
    unfilled_slots: int
