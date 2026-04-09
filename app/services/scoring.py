"""Deterministic scoring engine with config-driven weights.

score(c) = w1*overtime_headroom + w2*proximity + w3*clinical_fit
           - w4*float_penalty + w5*historical_acceptance

Weight priority: w1 >> w3 ~ w2 > w4 >> w5
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from app.schemas.common import ShiftLabel, UnitTypology


@dataclass
class ScoringWeights:
    overtime_headroom: float
    proximity: float
    clinical_fit: float
    float_penalty: float
    historical_acceptance: float


@dataclass
class ScoringConfig:
    weights: ScoringWeights
    max_relevant_distance_miles: float
    max_candidates_returned: int
    new_hire_months: int
    clinical_fit_scores: dict[str, float]
    float_penalty_values: dict[str, float]


def load_scoring_config(path: Path) -> ScoringConfig:
    """Load scoring configuration from YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    return ScoringConfig(
        weights=ScoringWeights(**raw["weights"]),
        max_relevant_distance_miles=raw["thresholds"]["max_relevant_distance_miles"],
        max_candidates_returned=raw["thresholds"]["max_candidates_returned"],
        new_hire_months=raw["thresholds"]["new_hire_months"],
        clinical_fit_scores=raw["clinical_fit_scores"],
        float_penalty_values=raw["float_penalty_values"],
    )


@dataclass
class ScoreResult:
    overtime_headroom: float
    proximity: float
    clinical_fit: float
    float_penalty: float
    historical_acceptance: float
    total: float


def compute_clinical_fit(
    candidate_home_typology: UnitTypology,
    candidate_cross_trained_unit_ids: list[str],
    target_unit_id: str,
    target_typology: UnitTypology,
    home_unit_id: str,
    config: ScoringConfig,
) -> float:
    """Score clinical fit based on unit typology matching.

    Subacute staff → subacute target: exact match (1.0)
    LT staff → LT target: exact match (1.0)
    Subacute staff → LT target: acceptable (0.8)
    LT staff → subacute target: severe penalty (0.0)
    Cross-trained for target: exact match (1.0)
    """
    # If this is their home unit, perfect fit
    if home_unit_id == target_unit_id:
        return config.clinical_fit_scores["exact_match"]

    # If cross-trained for the specific target unit, strong fit
    if target_unit_id in candidate_cross_trained_unit_ids:
        return config.clinical_fit_scores["exact_match"]

    # Typology-based matching
    if candidate_home_typology == target_typology:
        return config.clinical_fit_scores["exact_match"]

    if candidate_home_typology == UnitTypology.SUBACUTE and target_typology == UnitTypology.LT:
        return config.clinical_fit_scores["subacute_to_lt"]

    if candidate_home_typology == UnitTypology.LT and target_typology == UnitTypology.SUBACUTE:
        return config.clinical_fit_scores["lt_to_subacute"]

    return 0.0


def compute_float_penalty(
    home_unit_id: str,
    target_unit_id: str,
    candidate_home_typology: UnitTypology,
    target_typology: UnitTypology,
    hire_date: date,
    reference_date: date,
    config: ScoringConfig,
) -> float:
    """Compute float penalty — higher when floating staff away from home unit.

    New hires (< new_hire_months tenure) get an amplified penalty.
    """
    if home_unit_id == target_unit_id:
        return config.float_penalty_values["home_unit"]

    if candidate_home_typology == target_typology:
        penalty = config.float_penalty_values["same_typology"]
    else:
        penalty = config.float_penalty_values["cross_typology"]

    # Amplify penalty for new hires
    tenure_days = (reference_date - hire_date).days
    tenure_months = tenure_days / 30.44  # average days per month
    if tenure_months < config.new_hire_months:
        penalty *= config.float_penalty_values["new_hire_multiplier"]

    return min(penalty, 1.0)


def score_candidate(
    ot_headroom: float,
    proximity: float,
    clinical_fit: float,
    float_penalty: float,
    historical_acceptance: float,
    weights: ScoringWeights,
) -> ScoreResult:
    """Compute the weighted score for a candidate."""
    total = (
        weights.overtime_headroom * ot_headroom
        + weights.proximity * proximity
        + weights.clinical_fit * clinical_fit
        - weights.float_penalty * float_penalty
        + weights.historical_acceptance * historical_acceptance
    )

    return ScoreResult(
        overtime_headroom=round(ot_headroom, 4),
        proximity=round(proximity, 4),
        clinical_fit=round(clinical_fit, 4),
        float_penalty=round(float_penalty, 4),
        historical_acceptance=round(historical_acceptance, 4),
        total=round(total, 4),
    )
