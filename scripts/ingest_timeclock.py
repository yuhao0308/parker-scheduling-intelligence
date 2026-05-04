"""Load Kronos pay-period summaries from artifacts/timeclock/ into HoursLedger.

Discovers every distinct pay_period_start in the generated CSV and ingests
each one through the standard ``TimeClockSource`` -> ``HoursLedger`` adapter.
Run after ``scripts/seed_dev_data.py`` so the workload monitor's "worked"
segment is populated with realistic Kronos-shape data for demos.

Usage:
    python scripts/ingest_timeclock.py
    python scripts/ingest_timeclock.py --source-dir /path/to/csvs
"""
from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import date
from pathlib import Path

from app.db.session import async_session_factory
from app.integrations.timeclock.source import (
    DEFAULT_ARTIFACTS_DIR,
    PAY_PERIOD_FILE,
    CSVSource,
)
from app.services.timeclock_ingest import ingest_pay_period_summaries


def _discover_periods(csv_path: Path) -> list[date]:
    """Return sorted, unique pay_period_start values from the CSV."""
    if not csv_path.exists():
        raise FileNotFoundError(
            f"Pay period CSV not found at {csv_path}. "
            "Run scripts/generate_timeclock_data.py first."
        )
    starts: set[date] = set()
    with csv_path.open(newline="") as f:
        for row in csv.DictReader(f):
            starts.add(date.fromisoformat(row["pay_period_start"]))
    return sorted(starts)


async def _run(source_dir: Path) -> None:
    csv_path = source_dir / PAY_PERIOD_FILE
    periods = _discover_periods(csv_path)
    print(
        f"Discovered {len(periods)} pay periods in {csv_path.name}: "
        f"{periods[0].isoformat()} -> {periods[-1].isoformat()}"
    )

    source = CSVSource(artifacts_dir=source_dir)
    async with async_session_factory() as db:
        result = await ingest_pay_period_summaries(db, source, periods)
    print(
        f"HoursLedger sync: created={result.created} updated={result.updated} "
        f"total={result.total}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR,
        help=f"Directory containing the Kronos CSVs. Default: {DEFAULT_ARTIFACTS_DIR}",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.source_dir))


if __name__ == "__main__":
    main()
