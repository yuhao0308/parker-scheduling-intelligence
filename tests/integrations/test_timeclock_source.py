"""TimeClockSource interface tests.

Covers the round-trip: write CSVs via the generator -> read them back via
each of the three source impls -> verify identical results.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app.integrations.timeclock.aggregator import aggregate
from app.integrations.timeclock.generator import StaffSeed, generate_punches
from app.integrations.timeclock.source import (
    DAILY_TOTALS_FILE,
    PAY_PERIOD_FILE,
    PUNCHES_FILE,
    APISource,
    CSVSource,
    DBSource,
)
from scripts.generate_timeclock_data import (
    _write_daily_totals,
    _write_pay_period_summary,
    _write_punches,
)


@pytest.fixture
def fixture_dir(tmp_path: Path) -> Path:
    """Materialize a small dataset (one staff member, 14 days) to a temp dir."""
    staff = [
        StaffSeed(
            employee_id="CNA999",
            name="Test Person",
            license="CNA",
            employment_class="FT",
            home_unit_id="U-SA1",
            cross_trained_units=[],
        )
    ]
    start = date(2026, 4, 6)
    end = date(2026, 4, 19)
    punches = generate_punches(staff, start, end, seed=42)
    totals, summary = aggregate(punches, start, end)

    _write_punches(punches, tmp_path / PUNCHES_FILE)
    _write_daily_totals(totals, tmp_path / DAILY_TOTALS_FILE)
    _write_pay_period_summary(summary, tmp_path / PAY_PERIOD_FILE)
    return tmp_path


async def test_csv_source_round_trips_punches(fixture_dir):
    src = CSVSource(artifacts_dir=fixture_dir)
    punches = await src.fetch_punches(date(2026, 4, 6), date(2026, 4, 19))
    assert len(punches) > 0
    assert all(p.person_number == "CNA999" for p in punches)


async def test_csv_source_filters_by_date_range(fixture_dir):
    src = CSVSource(artifacts_dir=fixture_dir)
    # Narrow the window to one day — should drop the rest
    full = await src.fetch_punches(date(2026, 4, 6), date(2026, 4, 19))
    narrow = await src.fetch_punches(date(2026, 4, 10), date(2026, 4, 10))
    assert 0 < len(narrow) < len(full)


async def test_all_three_sources_return_identical_results(fixture_dir):
    csv_src = CSVSource(artifacts_dir=fixture_dir)
    api_src = APISource(backing=csv_src, simulated_latency_ms=0)
    db_src = DBSource(backing=csv_src, simulated_latency_ms=0)

    start = date(2026, 4, 6)
    end = date(2026, 4, 19)

    csv_punches = await csv_src.fetch_punches(start, end)
    api_punches = await api_src.fetch_punches(start, end)
    db_punches = await db_src.fetch_punches(start, end)

    assert len(csv_punches) == len(api_punches) == len(db_punches)
    for c, a, d in zip(csv_punches, api_punches, db_punches):
        assert c.punch_datetime == a.punch_datetime == d.punch_datetime
        assert c.direction == a.direction == d.direction


async def test_pay_period_summary_round_trips(fixture_dir):
    src = CSVSource(artifacts_dir=fixture_dir)
    summary = await src.fetch_pay_period_summary(date(2026, 4, 6))
    assert len(summary) == 1
    assert summary[0].person_number == "CNA999"
    assert summary[0].pay_period_end == date(2026, 4, 19)


async def test_missing_artifacts_raises_clear_error(tmp_path):
    src = CSVSource(artifacts_dir=tmp_path)
    with pytest.raises(FileNotFoundError, match="Run scripts/generate_timeclock_data.py"):
        await src.fetch_punches(date(2026, 4, 6), date(2026, 4, 19))
