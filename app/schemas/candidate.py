from __future__ import annotations

from typing import Dict

from pydantic import BaseModel

from app.schemas.common import EmploymentClass, LicenseType


class ScoreBreakdown(BaseModel):
    overtime_headroom: float
    proximity: float
    clinical_fit: float
    float_penalty: float
    historical_acceptance: float
    total: float


class ScoredCandidate(BaseModel):
    rank: int
    employee_id: str
    name: str
    license: LicenseType
    employment_class: EmploymentClass
    home_unit: str
    score: float
    score_breakdown: ScoreBreakdown
    rationale: str
    rationale_source: str  # "llm" or "template"


class FilterStats(BaseModel):
    total_pool: int
    passed_filter: int
    filtered_out: Dict[str, int]  # reason -> count
