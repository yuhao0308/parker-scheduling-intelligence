"""Tests for overtime headroom — the most financially critical logic.

Two distinct tracks:
  CNA/PCT/LPN: weekly OT after 37.5h
  RN: daily OT (2nd shift in op day) + biweekly OT (11th shift in 14-day cycle)
"""
from __future__ import annotations

from datetime import date

import pytest

from app.schemas.common import LicenseType, ShiftLabel
from app.services.overtime import calculate_ot_headroom


class TestStandardOvertimeCNA:
    """CNA/PCT/LPN weekly overtime after 37.5 hours."""

    def test_fresh_employee_full_headroom(self):
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=0.0,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 1.0
        assert ot is False

    def test_30_hours_partial_headroom(self):
        """30h + 8.25h shift = 38.25h → triggers OT, but still has 7.5h headroom."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=30.0,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == pytest.approx(7.5 / 37.5)
        assert ot is True  # 30 + 8.25 = 38.25 > 37.5

    def test_exactly_at_threshold(self):
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=37.5,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 0.0
        assert ot is True  # adding 8.25h would push over

    def test_already_in_ot(self):
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=45.0,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 0.0
        assert ot is True

    def test_just_under_threshold(self):
        """29.25h + 8.25h shift = 37.5h exactly. Should NOT trigger OT."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=29.25,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == pytest.approx(8.25 / 37.5)
        assert ot is False

    def test_just_over_threshold(self):
        """29.26h + 8.25h = 37.51h. SHOULD trigger OT."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=29.26,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert ot is True

    def test_lpn_same_rules_as_cna(self):
        """LPN at 20h → 20 + 8.25 = 28.25 < 37.5 → no OT."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.LPN, hours_this_cycle=20.0,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == pytest.approx(17.5 / 37.5)
        assert ot is False

    def test_pct_same_rules_as_cna(self):
        headroom, ot = calculate_ot_headroom(
            LicenseType.PCT, hours_this_cycle=37.5,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 0.0
        assert ot is True


class TestRnDualTrackOvertime:
    """RN: daily OT + biweekly OT evaluated concurrently."""

    def test_rn_no_shifts_full_headroom(self):
        """RN with 0 shifts: daily headroom=1.0, biweekly=(10-0)/10=1.0, min=1.0."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.RN, hours_this_cycle=0.0,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 1.0  # min(1.0, 10/10) = 1.0
        assert ot is False

    def test_rn_daily_ot_second_shift_same_day(self):
        """Second shift in same operational day → daily OT."""
        existing = [(date(2026, 4, 9), ShiftLabel.DAY)]
        headroom, ot = calculate_ot_headroom(
            LicenseType.RN, hours_this_cycle=8.25,
            shift_count_this_biweek=1,
            employee_shifts=existing,
            target_date=date(2026, 4, 9),
            target_label=ShiftLabel.EVENING,
        )
        assert headroom == 0.0  # daily OT drives headroom to 0
        assert ot is True

    def test_rn_biweekly_10th_shift_no_ot(self):
        """10th shift in biweek is still within threshold."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.RN, hours_this_cycle=74.25,
            shift_count_this_biweek=9,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        # daily: no existing shift today → 1.0
        # biweekly: (10-9)/10 = 0.1
        # min(1.0, 0.1) = 0.1
        assert headroom == pytest.approx(0.1)
        assert ot is False

    def test_rn_biweekly_11th_shift_triggers_ot(self):
        """11th shift in biweek → biweekly OT."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.RN, hours_this_cycle=82.5,
            shift_count_this_biweek=10,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        # daily: no existing shift today → 1.0
        # biweekly: (10-10)/10 = 0.0
        # min(1.0, 0.0) = 0.0
        assert headroom == 0.0
        assert ot is True

    def test_rn_both_tracks_trigger(self):
        """Both daily AND biweekly OT triggered."""
        existing = [(date(2026, 4, 9), ShiftLabel.DAY)]
        headroom, ot = calculate_ot_headroom(
            LicenseType.RN, hours_this_cycle=82.5,
            shift_count_this_biweek=10,
            employee_shifts=existing,
            target_date=date(2026, 4, 9),
            target_label=ShiftLabel.EVENING,
        )
        assert headroom == 0.0
        assert ot is True

    def test_rn_night_shift_cross_day_boundary(self):
        """Night shift on Apr 8 (op day Apr 9) counts for Apr 9 daily OT."""
        existing = [(date(2026, 4, 8), ShiftLabel.NIGHT)]
        headroom, ot = calculate_ot_headroom(
            LicenseType.RN, hours_this_cycle=8.25,
            shift_count_this_biweek=1,
            employee_shifts=existing,
            target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 0.0  # daily OT triggered
        assert ot is True
