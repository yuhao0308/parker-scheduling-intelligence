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
    """CNA/PCT/LPN: full headroom up to 37.5h, linear decay through 37.5–62.5h."""

    def test_fresh_employee_full_headroom(self):
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=0.0,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 1.0
        assert ot is False

    def test_30_hours_still_full_headroom(self):
        """30h is straight-time — no penalty. OT flag still fires if shift crosses 37.5h."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=30.0,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 1.0
        assert ot is True  # 30 + 8.25 = 38.25 > 37.5 → OT flag

    def test_at_threshold_no_penalty_yet(self):
        """At exactly 37.5h, headroom is still full — penalty starts only in the OT band."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=37.5,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 1.0
        assert ot is True

    def test_in_ot_band_partial_headroom(self):
        """45h is 7.5h into the 25h OT band → 1 - 7.5/25 = 0.7."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=45.0,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == pytest.approx(0.7)
        assert ot is True

    def test_deep_ot_band_lower_headroom(self):
        """55h is 17.5h into the 25h OT band → 1 - 17.5/25 = 0.3."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=55.0,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == pytest.approx(0.3)
        assert ot is True

    def test_at_soft_cap_zero_headroom(self):
        """At 62.5h (Sean's soft cap: +25h of OT), headroom drops to 0."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=62.5,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 0.0
        assert ot is True

    def test_beyond_soft_cap_zero_headroom(self):
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=65.0,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 0.0
        assert ot is True

    def test_just_under_threshold_no_ot_flag(self):
        """29.25h + 8.25h = 37.5h exactly. Should NOT trigger OT flag."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=29.25,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 1.0
        assert ot is False

    def test_just_over_threshold_flags_ot(self):
        """29.26h + 8.25h = 37.51h. SHOULD trigger OT flag (but headroom still 1.0)."""
        headroom, ot = calculate_ot_headroom(
            LicenseType.CNA, hours_this_cycle=29.26,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 1.0
        assert ot is True

    def test_lpn_same_rules_as_cna(self):
        headroom, ot = calculate_ot_headroom(
            LicenseType.LPN, hours_this_cycle=20.0,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        assert headroom == 1.0
        assert ot is False

    def test_pct_in_ot_band(self):
        headroom, ot = calculate_ot_headroom(
            LicenseType.PCT, hours_this_cycle=50.0,
            shift_count_this_biweek=0,
            employee_shifts=[], target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        # 50h is 12.5h into the 25h OT band → 1 - 12.5/25 = 0.5
        assert headroom == pytest.approx(0.5)
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
