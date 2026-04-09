"""Tests for shift_utils — operational day boundary and shift counting.

The 11PM boundary is the single most error-prone piece of time math.
"""
from __future__ import annotations

from datetime import date, datetime

from app.schemas.common import ShiftLabel
from app.services.shift_utils import (
    count_shifts_in_operational_day,
    get_operational_day,
    get_shift_date,
    is_rn_daily_ot,
    shift_to_datetime_range,
)


class TestGetOperationalDay:
    def test_night_shift_start_belongs_to_next_day(self):
        # 23:00 on Apr 8 → operational day Apr 9
        dt = datetime(2026, 4, 8, 23, 0)
        assert get_operational_day(dt) == date(2026, 4, 9)

    def test_early_morning_belongs_to_same_date(self):
        # 06:00 on Apr 9 → operational day Apr 9
        dt = datetime(2026, 4, 9, 6, 0)
        assert get_operational_day(dt) == date(2026, 4, 9)

    def test_day_shift_belongs_to_same_date(self):
        # 08:00 on Apr 9 → operational day Apr 9
        dt = datetime(2026, 4, 9, 8, 0)
        assert get_operational_day(dt) == date(2026, 4, 9)

    def test_evening_end_belongs_to_same_date(self):
        # 22:59 on Apr 9 → operational day Apr 9
        dt = datetime(2026, 4, 9, 22, 59)
        assert get_operational_day(dt) == date(2026, 4, 9)

    def test_just_before_boundary(self):
        # 22:59:59 on Apr 9 → still operational day Apr 9
        dt = datetime(2026, 4, 9, 22, 59, 59)
        assert get_operational_day(dt) == date(2026, 4, 9)

    def test_exact_boundary(self):
        # 23:00:00 on Apr 9 → operational day Apr 10
        dt = datetime(2026, 4, 9, 23, 0, 0)
        assert get_operational_day(dt) == date(2026, 4, 10)

    def test_midnight(self):
        # 00:00 on Apr 9 → operational day Apr 9
        dt = datetime(2026, 4, 9, 0, 0)
        assert get_operational_day(dt) == date(2026, 4, 9)


class TestGetShiftDate:
    def test_night_shift_advances_day(self):
        # NIGHT shift on calendar date Apr 8 → operational day Apr 9
        assert get_shift_date(date(2026, 4, 8), ShiftLabel.NIGHT) == date(2026, 4, 9)

    def test_day_shift_same_day(self):
        assert get_shift_date(date(2026, 4, 9), ShiftLabel.DAY) == date(2026, 4, 9)

    def test_evening_shift_same_day(self):
        assert get_shift_date(date(2026, 4, 9), ShiftLabel.EVENING) == date(2026, 4, 9)


class TestShiftToDatetimeRange:
    def test_night_shift_spans_midnight(self):
        start, end = shift_to_datetime_range(date(2026, 4, 8), ShiftLabel.NIGHT)
        assert start == datetime(2026, 4, 8, 23, 0)
        assert end == datetime(2026, 4, 9, 7, 15)

    def test_day_shift(self):
        start, end = shift_to_datetime_range(date(2026, 4, 9), ShiftLabel.DAY)
        assert start == datetime(2026, 4, 9, 7, 0)
        assert end == datetime(2026, 4, 9, 15, 15)

    def test_evening_shift(self):
        start, end = shift_to_datetime_range(date(2026, 4, 9), ShiftLabel.EVENING)
        assert start == datetime(2026, 4, 9, 15, 0)
        assert end == datetime(2026, 4, 9, 23, 15)


class TestCountShiftsInOperationalDay:
    def test_no_existing_shifts(self):
        count = count_shifts_in_operational_day(
            [], date(2026, 4, 9), ShiftLabel.DAY
        )
        assert count == 0

    def test_one_shift_same_operational_day(self):
        # Night shift on Apr 8 (op day Apr 9) + DAY shift on Apr 9 (op day Apr 9)
        existing = [(date(2026, 4, 8), ShiftLabel.NIGHT)]
        count = count_shifts_in_operational_day(
            existing, date(2026, 4, 9), ShiftLabel.DAY
        )
        assert count == 1

    def test_shifts_different_operational_day_not_counted(self):
        # DAY shift on Apr 8 (op day Apr 8) shouldn't count for Apr 9
        existing = [(date(2026, 4, 8), ShiftLabel.DAY)]
        count = count_shifts_in_operational_day(
            existing, date(2026, 4, 9), ShiftLabel.DAY
        )
        assert count == 0

    def test_two_shifts_same_operational_day(self):
        # Night (Apr 8 → op Apr 9) + DAY (Apr 9 → op Apr 9) = 2
        existing = [
            (date(2026, 4, 8), ShiftLabel.NIGHT),
            (date(2026, 4, 9), ShiftLabel.DAY),
        ]
        count = count_shifts_in_operational_day(
            existing, date(2026, 4, 9), ShiftLabel.EVENING
        )
        assert count == 2


class TestIsRnDailyOt:
    def test_no_existing_shift_not_ot(self):
        assert is_rn_daily_ot([], date(2026, 4, 9), ShiftLabel.DAY) is False

    def test_one_existing_shift_triggers_ot(self):
        existing = [(date(2026, 4, 9), ShiftLabel.DAY)]
        assert is_rn_daily_ot(existing, date(2026, 4, 9), ShiftLabel.EVENING) is True

    def test_night_and_day_same_op_day_triggers_ot(self):
        # Night on Apr 8 (op day Apr 9), adding DAY on Apr 9 (op day Apr 9)
        existing = [(date(2026, 4, 8), ShiftLabel.NIGHT)]
        assert is_rn_daily_ot(existing, date(2026, 4, 9), ShiftLabel.DAY) is True

    def test_different_op_day_no_ot(self):
        # DAY on Apr 8 (op day Apr 8), adding DAY on Apr 9 (op day Apr 9)
        existing = [(date(2026, 4, 8), ShiftLabel.DAY)]
        assert is_rn_daily_ot(existing, date(2026, 4, 9), ShiftLabel.DAY) is False
