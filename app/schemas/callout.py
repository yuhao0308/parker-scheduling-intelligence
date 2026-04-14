from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.candidate import FilterStats, ScoredCandidate
from app.schemas.common import ShiftLabel


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


class OverrideResponse(BaseModel):
    override_id: int
    recommendation_log_id: int
    selected_employee_id: str
    selected_rank: Optional[int]
