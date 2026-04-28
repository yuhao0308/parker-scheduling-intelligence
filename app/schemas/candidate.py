from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel

from app.schemas.common import EmploymentClass, LicenseType
from app.schemas.rationale import Rationale


class ScoreBreakdown(BaseModel):
    overtime_headroom: float
    proximity: float
    clinical_fit: float
    float_penalty: float
    total: float
    seniority: float = 0.0
    equity: float = 0.0
    willingness: float = 0.0


class ScoredCandidate(BaseModel):
    rank: int
    employee_id: str
    name: str
    license: LicenseType
    employment_class: EmploymentClass
    home_unit: str
    score: float
    score_breakdown: ScoreBreakdown
    rationale: Rationale
    rationale_source: str  # "llm" or "template"
    would_trigger_ot: bool
    ot_headroom_label: str
    hours_this_cycle: float
    shift_count_this_biweek: int
    # Month-level workload (mirrors workload monitor)
    scheduled_shifts_this_month: int = 0
    scheduled_hours_this_month: float = 0.0
    peak_week_hours: float = 0.0
    peak_biweekly_shifts: int = 0
    projected_overtime_hours: float = 0.0
    projected_overtime_shifts: int = 0
    # Fit + meta
    is_home_unit: bool = False
    home_unit_typology: Optional[str] = None
    target_unit_typology: Optional[str] = None
    clinical_fit_description: str = ""
    distance_miles: float = 0.0
    tenure_years: Optional[float] = None
    days_since_last_shift: Optional[int] = None
    # Callout-context positive signals (used by the UI's support badges).
    target_unit_shifts: int = 0
    has_adjacent_shift: bool = False


class FilterStats(BaseModel):
    total_pool: int
    passed_filter: int
    filtered_out: Dict[str, int]  # reason -> count
