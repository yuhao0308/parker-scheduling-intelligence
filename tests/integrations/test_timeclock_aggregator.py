"""Aggregator unit tests: rounding, meal deduct, missed punches, OT."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.integrations.timeclock.aggregator import (
    BIWEEKLY_OT_THRESHOLD,
    DAILY_OT_THRESHOLD,
    aggregate,
    apply_meal_deduction,
    collect_explicit_meals,
    pair_punches_into_segments,
    round_to_quarter_hour,
)
from app.integrations.timeclock.kronos_schema import (
    KronosPunchRecord,
    PayCode,
    PunchDirection,
    PunchSource,
    PunchType,
)


def _punch(
    emp: str = "CNA001",
    when: datetime = datetime(2026, 4, 10, 7, 0),
    direction: PunchDirection = PunchDirection.IN,
    punch_type: PunchType = PunchType.NORMAL,
    unit: str = "U-SA1",
    license: str = "CNA",
    override: str | None = None,
    edited: bool = False,
) -> KronosPunchRecord:
    return KronosPunchRecord(
        person_number=emp,
        person_name=f"Person {emp}",
        punch_datetime=when,
        direction=direction,
        punch_type=punch_type,
        labor_level_1="UNITED_HEBREW",
        labor_level_2=unit,
        labor_level_3=license,
        pay_code=PayCode.REG,
        source=PunchSource.TERMINAL,
        terminal_id=f"T-{unit}-01",
        override=override,
        edited=edited,
    )


# ---------- Rounding ----------


class TestRounding:
    """7-minute rounding rule (Kronos default + FLSA de minimis cap)."""

    @pytest.mark.parametrize(
        "input_minute,expected_minute,expected_hour_offset",
        [
            (53, 0, 1),    # :53 -> next hour :00 (7 min away)
            (54, 0, 1),    # :54 -> next hour :00 (6 min away)
            (7, 0, 0),     # :07 -> :00 (closer to :00 than :15)
            (8, 15, 0),    # :08 -> :15 (7 from :15)
            (22, 15, 0),   # :22 -> :15 (closer to :15 than :30)
            (23, 30, 0),   # :23 -> :30 (7 from :30)
            (37, 30, 0),   # :37 -> :30
            (38, 45, 0),   # :38 -> :45
            (52, 45, 0),   # :52 -> :45 (closer to :45 than :60)
        ],
    )
    def test_within_window_snaps_to_quarter(
        self, input_minute, expected_minute, expected_hour_offset
    ):
        dt = datetime(2026, 4, 10, 7, input_minute, 30)
        result = round_to_quarter_hour(dt)
        assert result.minute == expected_minute
        assert result.hour == 7 + expected_hour_offset
        assert result.second == 0

    def test_outside_window_keeps_original_time(self):
        # :30 is exactly on a quarter — stays put.
        dt = datetime(2026, 4, 10, 7, 30, 0)
        assert round_to_quarter_hour(dt).minute == 30


# ---------- Punch pairing ----------


class TestPunchPairing:
    """IN/OUT pairing into shift segments, including transfers and orphans."""

    def test_simple_in_out_produces_one_segment(self):
        punches = [
            _punch(when=datetime(2026, 4, 10, 7, 0), direction=PunchDirection.IN),
            _punch(when=datetime(2026, 4, 10, 15, 15), direction=PunchDirection.OUT),
        ]
        segments, orphans = pair_punches_into_segments(punches)
        assert len(segments) == 1
        assert len(orphans) == 0
        assert segments[0].duration_hours == pytest.approx(8.25)

    def test_meal_punches_dont_break_segments(self):
        punches = [
            _punch(when=datetime(2026, 4, 10, 7, 0), direction=PunchDirection.IN),
            _punch(
                when=datetime(2026, 4, 10, 11, 0),
                direction=PunchDirection.OUT,
                punch_type=PunchType.MEAL_START,
            ),
            _punch(
                when=datetime(2026, 4, 10, 11, 30),
                direction=PunchDirection.IN,
                punch_type=PunchType.MEAL_END,
            ),
            _punch(when=datetime(2026, 4, 10, 15, 15), direction=PunchDirection.OUT),
        ]
        segments, orphans = pair_punches_into_segments(punches)
        assert len(segments) == 1
        assert len(orphans) == 0

    def test_transfer_splits_into_two_segments(self):
        punches = [
            _punch(when=datetime(2026, 4, 10, 7, 0), direction=PunchDirection.IN, unit="U-SA1"),
            _punch(
                when=datetime(2026, 4, 10, 11, 0),
                direction=PunchDirection.OUT,
                punch_type=PunchType.TRANSFER,
                unit="U-SA1",
            ),
            _punch(
                when=datetime(2026, 4, 10, 11, 0),
                direction=PunchDirection.IN,
                unit="U-SA2",
            ),
            _punch(when=datetime(2026, 4, 10, 15, 15), direction=PunchDirection.OUT, unit="U-SA2"),
        ]
        segments, orphans = pair_punches_into_segments(punches)
        assert len(segments) == 2
        assert {s.labor_level_2 for s in segments} == {"U-SA1", "U-SA2"}

    def test_missing_out_punch_returns_orphan(self):
        # IN with no matching OUT is an orphan.
        punches = [
            _punch(when=datetime(2026, 4, 10, 7, 0), direction=PunchDirection.IN),
        ]
        segments, orphans = pair_punches_into_segments(punches)
        assert len(segments) == 0
        assert len(orphans) == 1


# ---------- Meal deduction ----------


class TestMealDeduction:
    """Auto-deduct on long shifts; explicit meals override auto-deduct."""

    def test_long_shift_with_no_meal_punches_gets_auto_deduct(self):
        punches = [
            _punch(when=datetime(2026, 4, 10, 7, 0), direction=PunchDirection.IN),
            _punch(when=datetime(2026, 4, 10, 15, 15), direction=PunchDirection.OUT),
        ]
        segments, _ = pair_punches_into_segments(punches)
        meals = collect_explicit_meals(punches)
        assert meals == {}
        deducted = apply_meal_deduction(segments, meals)
        # 8h 15m gross - 30min auto-deduct = 7h 45m paid
        assert deducted[0].duration_hours == pytest.approx(7.75)

    def test_explicit_meal_punches_override_auto_deduct(self):
        punches = [
            _punch(when=datetime(2026, 4, 10, 7, 0), direction=PunchDirection.IN),
            _punch(
                when=datetime(2026, 4, 10, 11, 0),
                direction=PunchDirection.OUT,
                punch_type=PunchType.MEAL_START,
            ),
            _punch(
                when=datetime(2026, 4, 10, 11, 15),
                direction=PunchDirection.IN,
                punch_type=PunchType.MEAL_END,
            ),
            _punch(when=datetime(2026, 4, 10, 15, 15), direction=PunchDirection.OUT),
        ]
        segments, _ = pair_punches_into_segments(punches)
        meals = collect_explicit_meals(punches)
        deducted = apply_meal_deduction(segments, meals)
        # Only 15-min meal taken => 8h 00m paid (vs 7h 45m auto-deduct)
        assert deducted[0].duration_hours == pytest.approx(8.0)

    def test_short_shift_no_meal_deduction(self):
        # 4-hour shift — under the 6-hour auto-deduct threshold
        punches = [
            _punch(when=datetime(2026, 4, 10, 9, 0), direction=PunchDirection.IN),
            _punch(when=datetime(2026, 4, 10, 13, 0), direction=PunchDirection.OUT),
        ]
        segments, _ = pair_punches_into_segments(punches)
        deducted = apply_meal_deduction(segments, collect_explicit_meals(punches))
        assert deducted[0].duration_hours == pytest.approx(4.0)


# ---------- Missed punches / auto-out ----------


class TestMissedPunches:
    """Forgotten clock-outs get auto-closed and surfaced in the period summary."""

    def test_missed_out_is_auto_closed(self):
        period_start = date(2026, 4, 6)
        period_end = date(2026, 4, 19)
        # IN with no OUT — should produce a daily total via auto-out
        punches = [
            _punch(when=datetime(2026, 4, 10, 7, 0), direction=PunchDirection.IN),
        ]
        totals, summary = aggregate(punches, period_start, period_end)
        # Auto-out runs the IN to ~8h 15m later, with meal deducted
        assert len(totals) == 1
        assert totals[0].pay_code == PayCode.REG
        assert totals[0].hours > 0
        assert summary[0].missed_punch_count == 1

    def test_normal_punches_have_no_missed_count(self):
        period_start = date(2026, 4, 6)
        period_end = date(2026, 4, 19)
        punches = [
            _punch(when=datetime(2026, 4, 10, 7, 0), direction=PunchDirection.IN),
            _punch(when=datetime(2026, 4, 10, 15, 15), direction=PunchDirection.OUT),
        ]
        _, summary = aggregate(punches, period_start, period_end)
        assert summary[0].missed_punch_count == 0


# ---------- Overtime ----------


class TestOvertime:
    """8/80 OT regime: daily 8h cap + biweekly 80h cap."""

    def test_daily_ot_splits_long_shift(self):
        # 10-hour shift, no meal deduct (use a 5-hour and a back-to-back).
        # Easier: build a 10h window ignoring meal punches.
        punches = [
            _punch(when=datetime(2026, 4, 10, 7, 0), direction=PunchDirection.IN),
            _punch(
                when=datetime(2026, 4, 10, 11, 0),
                direction=PunchDirection.OUT,
                punch_type=PunchType.MEAL_START,
            ),
            _punch(
                when=datetime(2026, 4, 10, 11, 0),  # zero-minute meal
                direction=PunchDirection.IN,
                punch_type=PunchType.MEAL_END,
            ),
            _punch(when=datetime(2026, 4, 10, 17, 0), direction=PunchDirection.OUT),
        ]
        totals, _ = aggregate(punches, date(2026, 4, 6), date(2026, 4, 19))
        reg = next(t for t in totals if t.pay_code == PayCode.REG)
        ot = next(t for t in totals if t.pay_code == PayCode.OT)
        assert reg.hours == pytest.approx(DAILY_OT_THRESHOLD)
        assert ot.hours == pytest.approx(2.0)

    def test_biweekly_80h_promotes_reg_to_ot(self):
        # Generate 11 shifts of 8h paid each = 88h => 80 REG + 8 OT
        period_start = date(2026, 4, 6)
        period_end = date(2026, 4, 19)
        punches = []
        for i in range(11):
            day = date(2026, 4, 6) + timedelta(days=i)
            # 8.5h gross with explicit 30-min meal -> 8h paid
            punches.append(_punch(emp="RN999", when=datetime.combine(day, datetime.min.time().replace(hour=7))))
            punches.append(
                _punch(
                    emp="RN999",
                    when=datetime(day.year, day.month, day.day, 11, 0),
                    direction=PunchDirection.OUT,
                    punch_type=PunchType.MEAL_START,
                )
            )
            punches.append(
                _punch(
                    emp="RN999",
                    when=datetime(day.year, day.month, day.day, 11, 30),
                    direction=PunchDirection.IN,
                    punch_type=PunchType.MEAL_END,
                )
            )
            punches.append(
                _punch(
                    emp="RN999",
                    when=datetime(day.year, day.month, day.day, 15, 30),
                    direction=PunchDirection.OUT,
                )
            )
        _, summary = aggregate(punches, period_start, period_end)
        s = summary[0]
        assert s.regular_hours == BIWEEKLY_OT_THRESHOLD
        assert s.overtime_hours == pytest.approx(8.0)
        assert s.total_paid_hours == pytest.approx(88.0)

    def test_under_80h_has_no_ot(self):
        period_start = date(2026, 4, 6)
        period_end = date(2026, 4, 19)
        # Only 5 shifts × 8h = 40h
        punches = []
        for i in range(5):
            day = date(2026, 4, 6) + timedelta(days=i)
            punches.append(
                _punch(emp="RN888", when=datetime(day.year, day.month, day.day, 7, 0))
            )
            punches.append(
                _punch(
                    emp="RN888",
                    when=datetime(day.year, day.month, day.day, 11, 0),
                    direction=PunchDirection.OUT,
                    punch_type=PunchType.MEAL_START,
                )
            )
            punches.append(
                _punch(
                    emp="RN888",
                    when=datetime(day.year, day.month, day.day, 11, 30),
                    direction=PunchDirection.IN,
                    punch_type=PunchType.MEAL_END,
                )
            )
            punches.append(
                _punch(
                    emp="RN888",
                    when=datetime(day.year, day.month, day.day, 15, 30),
                    direction=PunchDirection.OUT,
                )
            )
        _, summary = aggregate(punches, period_start, period_end)
        assert summary[0].overtime_hours == 0
        assert summary[0].regular_hours == pytest.approx(40.0)
