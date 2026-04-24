from __future__ import annotations

import enum
from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.candidate import FilterStats, ScoredCandidate
from app.schemas.common import EmploymentClass, LicenseType, ShiftLabel


class CalloutJobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class HITLFeedbackTag(str, enum.Enum):
    """Structured micro-feedback tags captured when the scheduler overrides
    the top recommendation. Used downstream to train the RL reward model.
    """

    UNDOCUMENTED_INTERPERSONAL = "undocumented_interpersonal"
    LIGHT_DUTY_REQUEST = "light_duty_request"
    CLINICAL_JUDGMENT = "clinical_judgment"
    STAFF_UNREACHABLE = "staff_unreachable"
    SCHEDULER_PREFERENCE = "scheduler_preference"
    AVAILABILITY_CONSTRAINT = "availability_constraint"
    OTHER = "other"


class CalloutRequest(BaseModel):
    callout_employee_id: str
    unit_id: str
    shift_date: date
    shift_label: ShiftLabel

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "callout_employee_id": "CNA100",
                "unit_id": "U-SA1",
                "shift_date": "2026-04-14",
                "shift_label": "DAY",
            }
        }
    )


class CalledOutEmployee(BaseModel):
    """Profile snapshot of the employee who called out — shown on the
    recommendation page so coordinators can compare against replacements.
    """

    employee_id: str
    name: str
    license: LicenseType
    employment_class: EmploymentClass
    home_unit_id: Optional[str] = None
    home_unit_name: Optional[str] = None
    hire_date: Optional[date] = None


class CalloutResponse(BaseModel):
    callout_id: int
    recommendation_log_id: int
    unit_id: str
    unit_name: str
    shift_date: date
    shift_label: ShiftLabel
    called_out_employee: CalledOutEmployee
    candidates: List[ScoredCandidate]
    filter_stats: FilterStats
    generated_at: datetime

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "callout_id": 12,
                "recommendation_log_id": 34,
                "unit_id": "U-SA1",
                "unit_name": "Subacute Unit 1",
                "shift_date": "2026-04-14",
                "shift_label": "DAY",
                "called_out_employee": {
                    "employee_id": "CNA100",
                    "name": "Daniel Griffin",
                    "license": "CNA",
                    "employment_class": "FT",
                    "home_unit_id": "U-SA1",
                    "home_unit_name": "Subacute Unit 1",
                    "hire_date": "2022-08-15",
                },
                "candidates": [
                    {
                        "rank": 1,
                        "employee_id": "CNA101",
                        "name": "Maria Santos",
                        "license": "CNA",
                        "employment_class": "FT",
                        "home_unit": "U-SA1",
                        "score": 0.94,
                        "score_breakdown": {
                            "overtime_headroom": 1.0,
                            "proximity": 0.89,
                            "clinical_fit": 1.0,
                            "float_penalty": 0.0,
                            "total": 0.9445,
                        },
                        "rationale": "- Hours: 29.3h of straight time remaining this week\n- Experience: CNA — Home unit match\n- Distance: 3.2 miles from facility",
                        "rationale_source": "template",
                    }
                ],
                "filter_stats": {
                    "total_pool": 18,
                    "passed_filter": 4,
                    "filtered_out": {
                        "license_mismatch": 10,
                        "already_scheduled_or_pto": 2,
                        "rest_window_violation": 2,
                    },
                },
                "generated_at": "2026-04-14T10:15:00Z",
            }
        }
    )


class OverrideRequest(BaseModel):
    recommendation_log_id: int
    selected_employee_id: str
    coordinator_id: str
    override_reason: Optional[str] = None
    feedback_tag: Optional[HITLFeedbackTag] = None


class OverrideResponse(BaseModel):
    override_id: int
    recommendation_log_id: int
    selected_employee_id: str
    selected_rank: Optional[int]
    writeback_status: Optional[str] = None
    writeback_detail: Optional[str] = None


class CalloutJobResponse(BaseModel):
    """Polling-friendly shape for the background recommendation pipeline.

    POST /callouts returns this immediately with status=RUNNING. Clients
    poll GET /callouts/{id} until status is COMPLETED (carrying the
    ranked candidates + filter stats) or FAILED (carrying error_message).
    """

    callout_id: int
    status: CalloutJobStatus
    unit_id: str
    unit_name: str
    shift_date: date
    shift_label: ShiftLabel
    called_out_employee: Optional[CalledOutEmployee] = None
    reported_at: datetime
    error_message: Optional[str] = None
    recommendation_log_id: Optional[int] = None
    candidates: Optional[List[ScoredCandidate]] = None
    filter_stats: Optional[FilterStats] = None
    generated_at: Optional[datetime] = None


class CalloutDayCount(BaseModel):
    """Per-date callout rollup feeding calendar red-dot indicators."""

    date: date
    total: int
    active: int  # callouts without an accepted replacement entry yet
