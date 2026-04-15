from __future__ import annotations

import enum
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.candidate import FilterStats, ScoredCandidate
from app.schemas.common import ShiftLabel


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


class CalloutResponse(BaseModel):
    callout_id: int
    recommendation_log_id: int
    unit_id: str
    unit_name: str
    shift_date: date
    shift_label: ShiftLabel
    candidates: List[ScoredCandidate]
    filter_stats: FilterStats
    generated_at: datetime


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
