"""Kronos WIM-aligned schema for time clock punches and totals.

Field names and value vocabularies (pay codes, punch types, sources) follow
Kronos Workforce Integration Manager conventions so that real client extracts
drop in with at most a column-rename. The three layers map directly to the
three exports a Kronos installation typically produces:

  - Punch Detail    -> KronosPunchRecord       (one row per IN/OUT event)
  - Daily Totals    -> KronosDailyTotal        (one row per employee/day/paycode/job)
  - Pay Period Sum  -> KronosPayPeriodSummary  (one row per employee per biweekly cycle)

All datetimes are naive local time (America/New_York). Kronos exports do not
carry timezone in punch fields; the facility timezone is implicit. Downstream
code that needs UTC must localize at the boundary.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class PunchDirection(str, enum.Enum):
    IN = "IN"
    OUT = "OUT"


class PunchType(str, enum.Enum):
    """Classification of a punch event.

    NORMAL covers shift-start and shift-end punches. MEAL_START/MEAL_END mark
    unpaid meal breaks (tracked when employees punch out for meals rather than
    relying on auto-deduct). TRANSFER is an in-shift unit/job change — the
    employee stays on the clock but their cost center switches.
    """

    NORMAL = "NORMAL"
    TRANSFER = "TRANSFER"
    MEAL_START = "MEAL_START"
    MEAL_END = "MEAL_END"


class PayCode(str, enum.Enum):
    """Kronos pay code vocabulary used by long-term-care payrolls."""

    REG = "REG"          # Regular hours
    OT = "OT"            # Overtime (1.5x)
    DT = "DT"            # Doubletime (2x; rare in LTC, used for mandatory holidays)
    HOL = "HOL"          # Worked holiday
    SICK = "SICK"        # Sick leave
    PTO = "PTO"          # Paid time off
    BEREAVE = "BEREAVE"  # Bereavement
    NCNS = "NCNS"        # No call no show — zero-hour record for audit


class PunchSource(str, enum.Enum):
    """Where the punch was recorded.

    A real Kronos install distinguishes hardware terminal vs. mobile vs.
    manual manager entry. We track this so demos can illustrate the
    well-known mobile reliability concern (employees clocking in without
    actually being on-site).
    """

    TERMINAL = "TERMINAL"  # Wall-mounted clock at the facility
    MOBILE = "MOBILE"      # App-based punch (geofence-checked but spoofable)
    MANUAL = "MANUAL"      # Manager entered after the fact
    PHONE = "PHONE"        # IVR call-in
    AUTO = "AUTO"          # System-generated (e.g., auto-out for missed punch)


class KronosPunchRecord(BaseModel):
    """One IN or OUT event from the Kronos punch detail export.

    Mirrors the Kronos WIM "Punches.csv" schema. ``person_number`` is the
    employee badge ID (matches our ``StaffMaster.employee_id``). Labor levels
    are Kronos's hierarchical cost center model — for United Hebrew we use
    facility/unit/position.
    """

    person_number: str = Field(..., description="Employee badge ID")
    person_name: str

    punch_datetime: datetime = Field(
        ..., description="Naive local time the punch was recorded"
    )
    direction: PunchDirection
    punch_type: PunchType = PunchType.NORMAL

    labor_level_1: str = Field(..., description="Facility (e.g., UNITED_HEBREW)")
    labor_level_2: str = Field(..., description="Unit / department (e.g., U-SA1)")
    labor_level_3: str = Field(..., description="Position / job code (e.g., RN)")

    pay_code: PayCode = PayCode.REG
    source: PunchSource = PunchSource.TERMINAL
    terminal_id: Optional[str] = None

    edited: bool = False
    edit_user: Optional[str] = None
    edit_reason: Optional[str] = None
    override: Optional[str] = Field(
        None,
        description="Override flag set when the system fabricated this punch — "
        "e.g., AUTO_OUT for a missed clock-out auto-closed by the rules engine",
    )


class KronosDailyTotal(BaseModel):
    """One row per (employee, work_date, pay_code, job) from the daily totals export.

    A single shift typically produces one REG row. A shift that crossed the
    daily OT threshold produces two rows (REG + OT). A shift with a mid-day
    transfer produces one row per cost center.

    ``work_date`` is the operational day the hours roll up to, not the calendar
    date the punches landed on — Kronos honors the facility's day boundary
    (United Hebrew uses 11 PM, see ``app.services.shift_utils``).
    """

    person_number: str
    work_date: date
    pay_code: PayCode
    hours: float = Field(..., ge=0.0, description="Quarter-hour rounded")

    job: str = Field(..., description="Combined cost center, e.g. UNITED_HEBREW/U-SA1/RN")
    labor_level_1: str
    labor_level_2: str
    labor_level_3: str

    shift_count: int = Field(
        1,
        ge=0,
        description="Number of distinct shifts contributing to this row "
        "(0 for PTO/SICK/NCNS rows where no shift was worked)",
    )


class KronosPayPeriodSummary(BaseModel):
    """Biweekly pay period roll-up — what payroll consumes.

    United Hebrew's biweekly cycle starts on a Monday. RN OT is dual-track
    (8/day OR 80/biweek), so this summary surfaces both regular and OT hours
    even though our internal HoursLedger collapses them.
    """

    person_number: str
    pay_period_start: date
    pay_period_end: date

    regular_hours: float = Field(..., ge=0.0)
    overtime_hours: float = Field(0.0, ge=0.0)
    doubletime_hours: float = Field(0.0, ge=0.0)
    holiday_hours: float = Field(0.0, ge=0.0)
    sick_hours: float = Field(0.0, ge=0.0)
    pto_hours: float = Field(0.0, ge=0.0)

    shift_count: int = Field(..., ge=0)
    missed_punch_count: int = Field(
        0,
        ge=0,
        description="Number of punches in this period that required manager edits "
        "to close — a flag for audit / employee performance review",
    )

    @property
    def total_paid_hours(self) -> float:
        return (
            self.regular_hours
            + self.overtime_hours
            + self.doubletime_hours
            + self.holiday_hours
            + self.sick_hours
            + self.pto_hours
        )
