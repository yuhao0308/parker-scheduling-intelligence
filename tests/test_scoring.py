"""Tests for the scoring engine."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.schemas.common import UnitTypology
from app.services.scoring import (
    ScoringWeights,
    compute_clinical_fit,
    compute_float_penalty,
    load_scoring_config,
    score_candidate,
)


@pytest.fixture
def weights():
    return ScoringWeights(
        overtime_headroom=0.50,
        proximity=0.05,
        clinical_fit=0.30,
        float_penalty=0.15,
    )


@pytest.fixture
def config():
    return load_scoring_config(Path("config/scoring_weights.yaml"))


class TestClinicalFit:
    def test_home_unit_exact_match(self, config):
        score = compute_clinical_fit(
            candidate_home_typology=UnitTypology.SUBACUTE,
            candidate_cross_trained_unit_ids=[],
            target_unit_id="U-SA1",
            target_typology=UnitTypology.SUBACUTE,
            home_unit_id="U-SA1",
            config=config,
        )
        assert score == 1.0

    def test_cross_trained_match(self, config):
        score = compute_clinical_fit(
            candidate_home_typology=UnitTypology.LT,
            candidate_cross_trained_unit_ids=["U-SA1"],
            target_unit_id="U-SA1",
            target_typology=UnitTypology.SUBACUTE,
            home_unit_id="U-LT1",
            config=config,
        )
        assert score == 1.0

    def test_same_typology(self, config):
        score = compute_clinical_fit(
            candidate_home_typology=UnitTypology.SUBACUTE,
            candidate_cross_trained_unit_ids=[],
            target_unit_id="U-SA2",
            target_typology=UnitTypology.SUBACUTE,
            home_unit_id="U-SA1",
            config=config,
        )
        assert score == 1.0

    def test_subacute_to_lt_acceptable(self, config):
        score = compute_clinical_fit(
            candidate_home_typology=UnitTypology.SUBACUTE,
            candidate_cross_trained_unit_ids=[],
            target_unit_id="U-LT1",
            target_typology=UnitTypology.LT,
            home_unit_id="U-SA1",
            config=config,
        )
        assert score == 0.8

    def test_lt_to_subacute_severe_penalty(self, config):
        score = compute_clinical_fit(
            candidate_home_typology=UnitTypology.LT,
            candidate_cross_trained_unit_ids=[],
            target_unit_id="U-SA1",
            target_typology=UnitTypology.SUBACUTE,
            home_unit_id="U-LT1",
            config=config,
        )
        assert score == 0.0


class TestFloatPenalty:
    def test_home_unit_no_penalty(self, config):
        penalty = compute_float_penalty(
            home_unit_id="U-SA1", target_unit_id="U-SA1",
            candidate_home_typology=UnitTypology.SUBACUTE,
            target_typology=UnitTypology.SUBACUTE,
            hire_date=date(2020, 1, 1), reference_date=date(2026, 4, 9),
            config=config,
        )
        assert penalty == 0.0

    def test_same_typology_moderate_penalty(self, config):
        penalty = compute_float_penalty(
            home_unit_id="U-SA1", target_unit_id="U-SA2",
            candidate_home_typology=UnitTypology.SUBACUTE,
            target_typology=UnitTypology.SUBACUTE,
            hire_date=date(2020, 1, 1), reference_date=date(2026, 4, 9),
            config=config,
        )
        assert penalty == 0.3

    def test_cross_typology_higher_penalty(self, config):
        penalty = compute_float_penalty(
            home_unit_id="U-SA1", target_unit_id="U-LT1",
            candidate_home_typology=UnitTypology.SUBACUTE,
            target_typology=UnitTypology.LT,
            hire_date=date(2020, 1, 1), reference_date=date(2026, 4, 9),
            config=config,
        )
        assert penalty == 0.6

    def test_new_hire_amplified_penalty(self, config):
        penalty = compute_float_penalty(
            home_unit_id="U-SA1", target_unit_id="U-SA2",
            candidate_home_typology=UnitTypology.SUBACUTE,
            target_typology=UnitTypology.SUBACUTE,
            hire_date=date(2026, 2, 1),  # ~2 months ago — new hire
            reference_date=date(2026, 4, 9),
            config=config,
        )
        # 0.3 * 1.5 = 0.45
        assert penalty == pytest.approx(0.45)


class TestScoreCandidate:
    def test_high_ot_headroom_wins(self, weights):
        """Candidate with more OT headroom should score higher, all else equal."""
        high = score_candidate(1.0, 0.5, 0.8, 0.0, weights)
        low = score_candidate(0.0, 0.5, 0.8, 0.0, weights)
        assert high.total > low.total

    def test_ot_headroom_dominates(self, weights):
        """OT headroom difference should translate directly to score delta."""
        big_ot = score_candidate(1.0, 0.5, 0.5, 0.3, weights)
        no_ot = score_candidate(0.0, 0.5, 0.5, 0.3, weights)
        assert big_ot.total - no_ot.total == pytest.approx(weights.overtime_headroom)

    def test_ot_beats_clinical_and_proximity_combined(self, weights):
        """OT dominates over clinical + proximity alone."""
        ot_champ = score_candidate(1.0, 0.0, 0.0, 0.0, weights)
        other_champ = score_candidate(0.0, 1.0, 1.0, 0.0, weights)
        assert ot_champ.total > other_champ.total

    def test_float_penalty_subtracts(self, weights):
        no_float = score_candidate(0.5, 0.5, 0.5, 0.0, weights)
        float_pen = score_candidate(0.5, 0.5, 0.5, 1.0, weights)
        assert no_float.total > float_pen.total

    def test_positive_weights_sum_to_one(self, weights):
        """Positive-signal weights must sum to 1.0 for interpretable scores."""
        total = (
            weights.overtime_headroom
            + weights.proximity
            + weights.clinical_fit
            + weights.float_penalty
            + weights.seniority
            + weights.equity
            + weights.willingness
        )
        assert total == pytest.approx(1.0)


class TestLoadScoringConfig:
    def test_loads_yaml(self):
        config = load_scoring_config(Path("config/scoring_weights.yaml"))
        assert config.weights.overtime_headroom == 0.45
        assert config.weights.proximity == 0.05
        assert config.weights.seniority == 0.08
        assert config.weights.equity == 0.05
        assert config.weights.willingness == 0.02
        assert config.max_relevant_distance_miles == 30
        assert config.clinical_fit_scores["lt_to_subacute"] == 0.0
