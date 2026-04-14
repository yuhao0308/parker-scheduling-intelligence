from __future__ import annotations

from datetime import date

import pytest

from app.services.workload import summarize_rn_schedule, summarize_standard_schedule


def test_standard_schedule_summarizes_peak_week_and_ot_hours():
    shifts = [
        date(2026, 4, 6),
        date(2026, 4, 7),
        date(2026, 4, 8),
        date(2026, 4, 9),
        date(2026, 4, 10),
    ]

    peak_week_hours, overtime_hours = summarize_standard_schedule(shifts)

    assert peak_week_hours == pytest.approx(41.25)
    assert overtime_hours == pytest.approx(3.75)


def test_rn_schedule_tracks_biweekly_shift_pressure():
    shifts = [
        (date(2026, 4, 6), "DAY"),
        (date(2026, 4, 7), "DAY"),
        (date(2026, 4, 8), "DAY"),
        (date(2026, 4, 9), "DAY"),
        (date(2026, 4, 10), "DAY"),
        (date(2026, 4, 11), "DAY"),
        (date(2026, 4, 12), "DAY"),
        (date(2026, 4, 13), "DAY"),
        (date(2026, 4, 14), "DAY"),
        (date(2026, 4, 15), "DAY"),
        (date(2026, 4, 16), "DAY"),
    ]

    double_shift_days, peak_biweekly_shifts, overtime_shifts = summarize_rn_schedule(
        shifts,
        cycle_anchor=date(2026, 4, 6),
    )

    assert double_shift_days == 0
    assert peak_biweekly_shifts == 11
    assert overtime_shifts == 1


def test_rn_schedule_detects_double_shift_days():
    shifts = [
        (date(2026, 4, 9), "DAY"),
        (date(2026, 4, 9), "EVENING"),
        (date(2026, 4, 10), "DAY"),
    ]

    double_shift_days, peak_biweekly_shifts, overtime_shifts = summarize_rn_schedule(
        shifts,
        cycle_anchor=date(2026, 4, 6),
    )

    assert double_shift_days == 1
    assert peak_biweekly_shifts == 3
    assert overtime_shifts == 0
