"""Deterministic scoring engine with config-driven weights.

score(c) = w1*overtime_headroom + w2*clinical_fit
           - w3*float_penalty + w4*proximity

Weight priority: w1 >> w2 > w3 >> w4
Overtime dominates per client guidance ("top of the priority" — Sean @ United Hebrew).
Proximity is retained only as a tiebreaker; it was never client-confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from app.schemas.common import ShiftLabel, UnitTypology


@dataclass
class ScoringWeights:
    overtime_headroom: float
    proximity: float
    clinical_fit: float
    float_penalty: float
    seniority: float = 0.0
    equity: float = 0.0
    willingness: float = 0.0


@dataclass
class ScoringConfig:
    weights: ScoringWeights
    max_relevant_distance_miles: float
    max_candidates_returned: int
    new_hire_months: int
    clinical_fit_scores: dict[str, float]
    float_penalty_values: dict[str, float]
    seniority_saturation_years: float = 10.0
    dormancy_threshold_days: int = 30


def load_scoring_config(path: Path) -> ScoringConfig:
    """Load scoring configuration from YAML file."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    thresholds = raw["thresholds"]
    return ScoringConfig(
        weights=ScoringWeights(**raw["weights"]),
        max_relevant_distance_miles=thresholds["max_relevant_distance_miles"],
        max_candidates_returned=thresholds["max_candidates_returned"],
        new_hire_months=thresholds["new_hire_months"],
        clinical_fit_scores=raw["clinical_fit_scores"],
        float_penalty_values=raw["float_penalty_values"],
        seniority_saturation_years=thresholds.get("seniority_saturation_years", 10.0),
        dormancy_threshold_days=thresholds.get("dormancy_threshold_days", 30),
    )


def compute_seniority_score(
    hire_date: date, reference_date: date, saturation_years: float
) -> float:
    """Linearly scale tenure from 0 to 1 up to a saturation horizon."""
    if saturation_years <= 0:
        return 0.0
    tenure_years = max(0.0, (reference_date - hire_date).days / 365.25)
    return min(1.0, tenure_years / saturation_years)


def compute_equity_score(
    employment_class: str,
    days_since_last_shift: int | None,
    threshold_days: int,
) -> float:
    """Surface dormant per-diem / contingent staff.

    Returns a 0..1 boost that is only non-zero once an eligible employee has
    been idle past `threshold_days`. Full-time / part-time staff do not receive
    the dormancy boost — the spec targets contingent workers sitting idle on
    the roster while full-timers accumulate overtime.
    """
    if employment_class != "PER_DIEM":
        return 0.0
    if days_since_last_shift is None:
        # Never worked — maximum dormancy boost so scheduler sees them.
        return 1.0
    if days_since_last_shift <= threshold_days:
        return 0.0
    # Ramp from 0 at threshold to 1 at 2x threshold.
    ratio = (days_since_last_shift - threshold_days) / float(threshold_days)
    return min(1.0, ratio)


@dataclass
class ScoreResult:
    overtime_headroom: float
    proximity: float
    clinical_fit: float
    float_penalty: float
    total: float
    seniority: float = 0.0
    equity: float = 0.0
    willingness: float = 0.0


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
    weights: ScoringWeights,
    seniority: float = 0.0,
    equity: float = 0.0,
    willingness: float = 0.0,
) -> ScoreResult:
    """Compute the weighted score for a candidate."""
    total = (
        weights.overtime_headroom * ot_headroom
        + weights.proximity * proximity
        + weights.clinical_fit * clinical_fit
        - weights.float_penalty * float_penalty
        + weights.seniority * seniority
        + weights.equity * equity
        + weights.willingness * willingness
    )

    return ScoreResult(
        overtime_headroom=round(ot_headroom, 4),
        proximity=round(proximity, 4),
        clinical_fit=round(clinical_fit, 4),
        float_penalty=round(float_penalty, 4),
        seniority=round(seniority, 4),
        equity=round(equity, 4),
        willingness=round(willingness, 4),
        total=round(total, 4),
    )
