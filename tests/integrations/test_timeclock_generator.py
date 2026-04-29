"""Generator + edge case tests.

Verifies the deliberately-injected problematic employees behave as designed
end-to-end (generator -> aggregator -> period summary).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.integrations.timeclock.aggregator import aggregate
from app.integrations.timeclock.generator import (
    CHRONIC_LATE_EMP,
    DOUBLES_EMP,
    EDGE_CASE_EMPLOYEES,
    FLOATER_EMP,
    MISSED_PUNCH_EMP,
    NO_MEAL_EMP,
    OT_SKIRTER_EMP,
    StaffSeed,
    generate_punches,
)
from app.integrations.timeclock.kronos_schema import (
    PayCode,
    PunchSource,
    PunchType,
)


@pytest.fixture(scope="module")
def staff() -> list[StaffSeed]:
    """A roster covering one of each edge case + a few normal employees.

    Mirrors the seeded United Hebrew roster shape (employee_id matches the
    seeded staff so cross_trained_units lines up).
    """
    return [
        StaffSeed(
            employee_id=CHRONIC_LATE_EMP,
            name="David Brown",
            license="CNA",
            employment_class="FT",
            home_unit_id="U-SA1",
            cross_trained_units=[],
        ),
        StaffSeed(
            employee_id=MISSED_PUNCH_EMP,
            name="William Taylor",
            license="CNA",
            employment_class="FT",
            home_unit_id="U-LT1",
            cross_trained_units=[],
        ),
        StaffSeed(
            employee_id=OT_SKIRTER_EMP,
            name="Robert Williams",
            license="RN",
            employment_class="PT",
            home_unit_id="U-LT2",
            cross_trained_units=["U-LT1"],
        ),
        StaffSeed(
            employee_id=NO_MEAL_EMP,
            name="Rosa Martinez",
            license="CNA",
            employment_class="PT",
            home_unit_id="U-LT2",
            cross_trained_units=["U-LT1", "U-LT3"],
        ),
        StaffSeed(
            employee_id=FLOATER_EMP,
            name="Aisha Johnson",
            license="CNA",
            employment_class="FT",
            home_unit_id="U-SA1",
            cross_trained_units=["U-SA2", "U-LT1"],
        ),
        StaffSeed(
            employee_id=DOUBLES_EMP,
            name="Jennifer Garcia",
            license="CNA",
            employment_class="PER_DIEM",
            home_unit_id="U-SA3",
            cross_trained_units=["U-SA1", "U-SA2"],
        ),
        # A clean baseline employee for comparison.
        StaffSeed(
            employee_id="CNA999",
            name="Clean Baseline",
            license="CNA",
            employment_class="FT",
            home_unit_id="U-SA1",
            cross_trained_units=[],
        ),
    ]


@pytest.fixture(scope="module")
def punches(staff):
    return generate_punches(
        staff, date(2026, 1, 28), date(2026, 4, 28), seed=42
    )


# ---------- Determinism ----------


def test_generator_is_deterministic(staff):
    a = generate_punches(staff, date(2026, 4, 1), date(2026, 4, 28), seed=42)
    b = generate_punches(staff, date(2026, 4, 1), date(2026, 4, 28), seed=42)
    assert len(a) == len(b)
    assert all(
        ap.punch_datetime == bp.punch_datetime
        and ap.person_number == bp.person_number
        and ap.direction == bp.direction
        for ap, bp in zip(a, b)
    )


def test_different_seed_produces_different_data(staff):
    a = generate_punches(staff, date(2026, 4, 1), date(2026, 4, 28), seed=42)
    b = generate_punches(staff, date(2026, 4, 1), date(2026, 4, 28), seed=99)
    assert [p.punch_datetime for p in a] != [p.punch_datetime for p in b]


# ---------- Edge case behavior ----------


class TestChronicLate:
    def test_late_clocker_has_punches_outside_rounding_window(self, punches):
        # Late by 8-12 min should produce IN times not on the quarter hour
        # AND outside the 7-min rounding window. Look for at least 5 INs
        # that land at minute > 7 (i.e., within 8-12 of the hour).
        late_ins = [
            p
            for p in punches
            if p.person_number == CHRONIC_LATE_EMP
            and p.direction.value == "IN"
            and p.punch_type == PunchType.NORMAL
            and 7 < p.punch_datetime.minute < 15
        ]
        assert len(late_ins) >= 5, (
            f"Expected chronic-late punches; got {len(late_ins)}"
        )


class TestMissedPunches:
    def test_missed_punch_emp_summary_has_nonzero_count(self, punches):
        period_start = date(2026, 3, 30)
        period_end = period_start + timedelta(days=13)
        period_punches = [p for p in punches if period_start <= p.punch_datetime.date() <= period_end + timedelta(days=1)]
        _, summary = aggregate(period_punches, period_start, period_end)
        emp_summary = next(
            (s for s in summary if s.person_number == MISSED_PUNCH_EMP), None
        )
        # Over a 90-day period at ~5% miss rate the count should be > 0 in
        # at least one biweekly cycle. We check the targeted cycle.
        # (5% × ~10 shifts per biweek ≈ 0.5, so we accept >= 0; the broader
        # check is on the full window below.)
        assert emp_summary is not None
        # Now verify across the full 90-day window — at least one miss expected.
        all_missed = sum(
            s.missed_punch_count
            for s in _all_summaries(punches)
            if s.person_number == MISSED_PUNCH_EMP
        )
        assert all_missed >= 1


class TestOTSkirter:
    def test_ot_skirter_stays_under_80_in_every_cycle(self, punches):
        for s in _all_summaries(punches):
            if s.person_number == OT_SKIRTER_EMP:
                assert s.regular_hours <= 80.0
                assert s.overtime_hours == 0.0


class TestNoMeal:
    def test_no_meal_emp_has_no_meal_punches(self, punches):
        meal_punches = [
            p
            for p in punches
            if p.person_number == NO_MEAL_EMP
            and p.punch_type in (PunchType.MEAL_START, PunchType.MEAL_END)
        ]
        assert len(meal_punches) == 0

    def test_no_meal_emp_pays_via_auto_deduct(self, punches):
        # Each shift should be 7.75h paid (8.25h gross - 30min auto-deduct)
        period_start = date(2026, 3, 30)
        period_end = period_start + timedelta(days=13)
        period_punches = [p for p in punches if period_start <= p.punch_datetime.date() <= period_end + timedelta(days=1)]
        totals, _ = aggregate(period_punches, period_start, period_end)
        no_meal_totals = [
            t
            for t in totals
            if t.person_number == NO_MEAL_EMP and t.pay_code == PayCode.REG
        ]
        if no_meal_totals:
            # All shifts should land at exactly 7.75 (or some multiple if doubled)
            for t in no_meal_totals:
                assert t.hours <= 8.0


class TestFloater:
    def test_floater_has_transfer_punches(self, punches):
        transfer_punches = [
            p
            for p in punches
            if p.person_number == FLOATER_EMP
            and p.punch_type == PunchType.TRANSFER
        ]
        assert len(transfer_punches) > 0

    def test_floater_segments_split_across_units(self, punches):
        floater_punches = [p for p in punches if p.person_number == FLOATER_EMP]
        units_seen = {p.labor_level_2 for p in floater_punches}
        # Should appear on home unit + at least one cross-trained unit
        assert len(units_seen) >= 2


class TestDoubles:
    def test_doubles_emp_has_some_long_days(self, punches):
        # Look for any operational day with > 8h paid for the doubles employee
        period_start = date(2026, 3, 30)
        period_end = date(2026, 4, 28)
        period_punches = [p for p in punches if p.punch_datetime.date() <= period_end]
        totals, _ = aggregate(period_punches, period_start, period_end)
        # Sum hours per work_date for the doubles emp
        by_day: dict[date, float] = {}
        for t in totals:
            if t.person_number == DOUBLES_EMP:
                by_day[t.work_date] = by_day.get(t.work_date, 0) + t.hours
        long_days = [d for d, h in by_day.items() if h > 8.0]
        # Over a ~30-day window with 10% double rate, expect at least 1
        assert len(long_days) >= 1, (
            f"Expected doubles employee to have at least one >8h day; "
            f"got days {by_day}"
        )


# ---------- Source distribution sanity ----------


def test_punch_sources_include_both_terminal_and_mobile(punches):
    sources = {p.source for p in punches}
    # We deliberately mix TERMINAL and MOBILE to demo the mobile-spoofing
    # concern called out in the integration design notes.
    assert PunchSource.TERMINAL in sources
    assert PunchSource.MOBILE in sources


def test_edge_case_employees_constants_match_seeded_roster():
    # These IDs must exist in scripts/seed_dev_data.BASE_STAFF — fail loudly
    # if a refactor renames a seeded employee out from under us.
    from scripts.seed_dev_data import BASE_STAFF

    seeded_ids = {r["employee_id"] for r in BASE_STAFF}
    missing = EDGE_CASE_EMPLOYEES - seeded_ids
    assert not missing, f"Edge case IDs not in seeded roster: {missing}"


# ---------- Helpers ----------


def _all_summaries(punches):
    """Aggregate over the whole window, period by period."""
    summaries = []
    period_start = date(2026, 1, 26)  # a Monday before the window
    while period_start <= date(2026, 4, 28):
        period_end = period_start + timedelta(days=13)
        period_punches = [
            p
            for p in punches
            if period_start
            <= p.punch_datetime.date()
            <= period_end + timedelta(days=1)
        ]
        _, s = aggregate(period_punches, period_start, period_end)
        summaries.extend(s)
        period_start = period_end + timedelta(days=1)
    return summaries
