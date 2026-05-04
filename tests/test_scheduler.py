from __future__ import annotations

from collections import defaultdict
from datetime import date

from app.models.unit import Unit
from app.models.unit import UnitTypology as ModelUnitTypology
from app.schemas.common import LicenseType, ShiftLabel, UnitTypology
from app.services.filter import CandidateRecord
from app.services.scheduler import _assign_one
from app.services.scoring import ScoringConfig, ScoringWeights


def _candidate(employee_id: str, license_type: LicenseType = LicenseType.CNA):
    return CandidateRecord(
        employee_id=employee_id,
        name=employee_id,
        license=license_type,
        employment_class="FT",
        zip_code="10801",
        home_unit_id="U-SA1",
        home_unit_typology="SUBACUTE",
        cross_trained_unit_ids=[],
        hire_date=date(2020, 1, 1),
        is_active=True,
    )


def _scoring_config():
    return ScoringConfig(
        weights=ScoringWeights(
            overtime_headroom=10.0,
            proximity=0.0,
            clinical_fit=1.0,
            float_penalty=1.0,
        ),
        max_relevant_distance_miles=25.0,
        max_candidates_returned=5,
        new_hire_months=6,
        clinical_fit_scores={
            "exact_match": 1.0,
            "subacute_to_lt": 0.8,
            "lt_to_subacute": 0.0,
        },
        float_penalty_values={
            "home_unit": 0.0,
            "same_typology": 0.2,
            "cross_typology": 0.6,
            "new_hire_multiplier": 1.5,
        },
    )


def _unit():
    return Unit(
        unit_id="U-SA1",
        name="Subacute 1",
        typology=ModelUnitTypology.SUBACUTE,
        required_ratio=1.0,
        is_active=True,
    )


def test_scheduler_prefers_non_ot_weekly_candidate_when_available():
    current_date = date(2026, 5, 6)
    week_num = current_date.isocalendar()[1]
    candidate_at_ot_edge = _candidate("CNA_OT_EDGE")
    candidate_with_capacity = _candidate("CNA_CAPACITY")
    weekly_hours = defaultdict(float)
    weekly_hours[(candidate_at_ot_edge.employee_id, week_num)] = 33.0

    assigned = _assign_one(
        candidates=[candidate_at_ot_edge, candidate_with_capacity],
        required_bucket="certified",
        unit=_unit(),
        unit_typology=UnitTypology.SUBACUTE,
        current_date=current_date,
        shift_label=ShiftLabel.DAY,
        week_num=week_num,
        weekly_hours=weekly_hours,
        biweekly_shifts=defaultdict(int),
        daily_shifts=defaultdict(list),
        base_hours_by_cycle={},
        scoring_config=_scoring_config(),
        settings=None,
        db=None,
    )

    assert assigned == candidate_with_capacity


def test_scheduler_falls_back_to_ot_candidate_for_coverage():
    current_date = date(2026, 5, 6)
    week_num = current_date.isocalendar()[1]
    candidate = _candidate("CNA_ONLY")
    weekly_hours = defaultdict(float)
    weekly_hours[(candidate.employee_id, week_num)] = 33.0

    assigned = _assign_one(
        candidates=[candidate],
        required_bucket="certified",
        unit=_unit(),
        unit_typology=UnitTypology.SUBACUTE,
        current_date=current_date,
        shift_label=ShiftLabel.DAY,
        week_num=week_num,
        weekly_hours=weekly_hours,
        biweekly_shifts=defaultdict(int),
        daily_shifts=defaultdict(list),
        base_hours_by_cycle={},
        scoring_config=_scoring_config(),
        settings=None,
        db=None,
    )

    assert assigned == candidate
