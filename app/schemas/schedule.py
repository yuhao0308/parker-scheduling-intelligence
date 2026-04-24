from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

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
    entry_id: Optional[int] = None
    confirmation_status: str = "UNSENT"


class ShiftSlotOut(BaseModel):
    unit_id: str
    unit_name: str
    shift_date: str
    shift_label: str
    # "fully_staffed" | "partially_staffed" | "callout" | "unassigned"
    status: str
    assigned_employees: List[AssignedEmployeeOut]
    callout_count: int
    callout_employee_ids: List[str] = []
    required_count: int = 0
    unresolved_callout_count: int = 0


class DayScheduleOut(BaseModel):
    date: str
    slots: List[ShiftSlotOut]


class MonthlyScheduleOut(BaseModel):
    year: int
    month: int
    days: List[DayScheduleOut]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "year": 2026,
                "month": 4,
                "days": [
                    {
                        "date": "2026-04-01",
                        "slots": [
                            {
                                "unit_id": "U-SA1",
                                "unit_name": "Subacute Unit 1",
                                "shift_date": "2026-04-01",
                                "shift_label": "DAY",
                                "status": "fully_staffed",
                                "assigned_employees": [
                                    {
                                        "employee_id": "RN200",
                                        "name": "Dana Brown",
                                        "license": "RN",
                                    }
                                ],
                                "callout_count": 0,
                                "callout_employee_ids": [],
                            }
                        ],
                    }
                ],
            }
        }
    )


class WorkHoursSummaryOut(BaseModel):
    employee_count: int
    total_scheduled_hours: float
    average_scheduled_hours: float
    employees_near_ot: int
    employees_in_ot: int
    employees_high_ot: int
    total_float_shifts: int


class EmployeeWorkHoursOut(BaseModel):
    employee_id: str
    name: str
    license: str
    employment_class: str
    home_unit_id: Optional[str] = None
    current_cycle_hours: float
    current_cycle_shifts: int
    scheduled_hours: float
    scheduled_shifts: int
    peak_week_hours: float
    projected_overtime_hours: float
    peak_biweekly_shifts: int
    projected_overtime_shifts: int
    double_shift_days: int
    home_unit_shifts: int
    float_shifts: int
    callout_count: int
    primary_unit_id: Optional[str] = None
    scheduled_unit_ids: List[str] = []
    overtime_status: str
    overtime_detail: str


class WorkHoursSnapshotOut(BaseModel):
    year: int
    month: int
    summary: WorkHoursSummaryOut
    employees: List[EmployeeWorkHoursOut]


class GenerateScheduleRequest(BaseModel):
    year: int
    month: int
    staff_count_override: Optional[int] = None
    employee_pool: Optional[List[str]] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "year": 2026,
                "month": 4,
                "staff_count_override": 20,
            }
        }
    )


class ScheduleGenerationResult(BaseModel):
    entries_created: int
    warnings: List[str]
    scenario: str
    unfilled_slots: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "entries_created": 1080,
                "warnings": [],
                "scenario": "ideal",
                "unfilled_slots": 0,
            }
        }
    )


class RegenerateWeekRequest(BaseModel):
    week_start: date
    employee_pool: List[str]
    preserve_responded: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "week_start": "2026-04-20",
                "employee_pool": ["RN001", "RN002", "CNA007"],
                "preserve_responded": True,
            }
        }
    )


class RegenerateWeekResult(BaseModel):
    week_start: date
    entries_created: int
    entries_preserved: int
    warnings: List[str]
    unfilled_slots: int


class AutogenSubmitRequest(BaseModel):
    week_start: date
    employee_pool: List[str]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "week_start": "2026-04-20",
                "employee_pool": ["RN001", "CNA007"],
            }
        }
    )


class AutogenSubmitResult(BaseModel):
    week_start: date
    entries_generated: int
    entries_preserved: int
    notifications_sent: int
    unfilled_slots: int
    warnings: List[str]


class MonthlyAutogenSubmitRequest(BaseModel):
    year: int
    month: int
    employee_pool: List[str]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "year": 2026,
                "month": 4,
                "employee_pool": ["RN001", "CNA007"],
            }
        }
    )


class MonthlyAutogenSubmitResult(BaseModel):
    year: int
    month: int
    entries_generated: int
    notifications_sent: int
    unfilled_slots: int
    warnings: List[str]
