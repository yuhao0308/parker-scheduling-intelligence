from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from app.schemas.callout import CalloutRequest
from app.schemas.common import LicenseType, ShiftLabel, UnitTypology
from app.schemas.schedule import GenerateScheduleRequest


class UnitSeed(BaseModel):
    unit_id: str
    name: str
    typology: UnitTypology
    required_ratio: float = 1.0
    is_active: bool = True


class StaffSeed(BaseModel):
    employee_id: str
    name: str
    license: LicenseType
    employment_class: str
    zip_code: str
    home_unit_id: str
    hire_date: date
    cross_trained_unit_ids: List[str] = Field(default_factory=list)
    is_active: bool = True


class HoursLedgerSeed(BaseModel):
    employee_id: str
    cycle_start_date: date
    hours_this_cycle: float
    shift_count_this_biweek: int = 0


class ScheduleEntrySeed(BaseModel):
    employee_id: str
    unit_id: str
    shift_date: date
    shift_label: ShiftLabel
    is_published: bool = True
    is_clocked_in: Optional[bool] = None


class PTOEntrySeed(BaseModel):
    employee_id: str
    start_date: date
    end_date: date


class UnitExclusionSeed(BaseModel):
    employee_id: str
    unit_id: str
    reason: str
    effective_from: date
    effective_until: Optional[date] = None


class ScenarioSetup(BaseModel):
    units: List[UnitSeed]
    staff: List[StaffSeed]
    hours_ledgers: List[HoursLedgerSeed] = Field(default_factory=list)
    schedule_entries: List[ScheduleEntrySeed] = Field(default_factory=list)
    pto_entries: List[PTOEntrySeed] = Field(default_factory=list)
    exclusions: List[UnitExclusionSeed] = Field(default_factory=list)


class CalloutActionSpec(BaseModel):
    kind: Literal["callout"]
    request: CalloutRequest


class GenerateScheduleActionSpec(BaseModel):
    kind: Literal["generate_schedule"]
    request: GenerateScheduleRequest
    fetch_monthly: bool = True
    fetch_work_hours: bool = True


ScenarioAction = Annotated[
    Union[CalloutActionSpec, GenerateScheduleActionSpec],
    Field(discriminator="kind"),
]


class ScenarioAssertion(BaseModel):
    kind: str
    description: str
    params: dict[str, Any] = Field(default_factory=dict)


class ScenarioSpec(BaseModel):
    id: str
    title: str
    business_rule: str
    result_classification: Literal["pass", "gap"]
    setup: ScenarioSetup
    action: ScenarioAction
    expected_assertions: List[ScenarioAssertion]


class AssertionResult(BaseModel):
    kind: str
    description: str
    passed: bool
    detail: str


class ScenarioResult(BaseModel):
    id: str
    title: str
    business_rule: str
    expected_classification: Literal["pass", "gap"]
    actual_classification: Literal["pass", "gap", "fail"]
    assertions: List[AssertionResult]
    request: dict[str, Any]
    responses: dict[str, Any]


class ScenarioRunReport(BaseModel):
    generated_at: datetime
    scenarios: List[ScenarioResult]
    summary: dict[str, int]
