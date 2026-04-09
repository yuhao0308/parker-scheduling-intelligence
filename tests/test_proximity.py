"""Tests for proximity estimation."""
from __future__ import annotations

import pytest

from app.services.proximity import estimate_distance_miles, proximity_score


class TestEstimateDistance:
    def test_same_zip_zero_distance(self):
        d = estimate_distance_miles("11375", "11375")
        assert d == pytest.approx(0.0, abs=0.1)

    def test_nearby_zips(self):
        # 11375 (Forest Hills) to 11432 (Jamaica) — a few miles
        d = estimate_distance_miles("11375", "11432")
        assert 0.5 < d < 10.0

    def test_farther_zips(self):
        # 11375 (Forest Hills) to 10301 (Staten Island) — 15-20 miles
        d = estimate_distance_miles("11375", "10301")
        assert 10.0 < d < 30.0

    def test_unknown_zip_returns_default(self):
        d = estimate_distance_miles("00000", "11375")
        assert d == 50.0


class TestProximityScore:
    def test_zero_distance_is_one(self):
        assert proximity_score(0.0) == 1.0

    def test_max_distance_is_zero(self):
        assert proximity_score(30.0, max_distance=30.0) == 0.0

    def test_beyond_max_is_zero(self):
        assert proximity_score(50.0, max_distance=30.0) == 0.0

    def test_half_distance_is_half(self):
        assert proximity_score(15.0, max_distance=30.0) == pytest.approx(0.5)

    def test_custom_max_distance(self):
        assert proximity_score(10.0, max_distance=20.0) == pytest.approx(0.5)
