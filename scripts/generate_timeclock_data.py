"""Materialize Kronos-format dummy time clock CSVs to artifacts/timeclock/.

Generates 90 days of punch history ending on today's date for the seeded
United Hebrew roster, runs the aggregator to derive daily totals and
biweekly summaries, and writes all three layers to CSV. Output files are
consumed by ``app.integrations.timeclock.source.CSVSource`` and the API/DB
stub variants behind the same interface.

The default end-date is ``date.today()``, resolved at call time. This
mirrors a real Kronos integration: clock data is always "history through
right now", and re-running the generator the next day captures the new
day. ``seed_dev_data.py`` invokes this script's ``generate_and_write``
helper before its time-clock ingest step so a fresh ``python
scripts/seed_dev_data.py`` always has data ending today.

Usage:
    python scripts/generate_timeclock_data.py
    python scripts/generate_timeclock_data.py --days 30 --seed 7
    python scripts/generate_timeclock_data.py --end 2026-05-15 --days 60
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

from app.integrations.timeclock.aggregator import aggregate
from app.integrations.timeclock.generator import StaffSeed, generate_punches
from app.integrations.timeclock.source import (
    DAILY_TOTALS_FILE,
    DEFAULT_ARTIFACTS_DIR,
    PAY_PERIOD_FILE,
    PUNCHES_FILE,
)
from scripts.seed_dev_data import build_staff_records

DEFAULT_DAYS = 90
PAY_PERIOD_LENGTH_DAYS = 14


def _staff_seeds() -> list[StaffSeed]:
    return [
        StaffSeed(
            employee_id=str(r["employee_id"]),
            name=str(r["name"]),
            license=str(r["license"]),
            employment_class=str(r["employment_class"]),
            home_unit_id=str(r["home_unit_id"]),
            cross_trained_units=list(r.get("cross_trained_units") or []),
        )
        for r in build_staff_records()
    ]


def _write_punches(rows, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "person_number",
                "person_name",
                "punch_datetime",
                "direction",
                "punch_type",
                "labor_level_1",
                "labor_level_2",
                "labor_level_3",
                "pay_code",
                "source",
                "terminal_id",
                "edited",
                "edit_user",
                "edit_reason",
                "override",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.person_number,
                    r.person_name,
                    r.punch_datetime.isoformat(),
                    r.direction.value,
                    r.punch_type.value,
                    r.labor_level_1,
                    r.labor_level_2,
                    r.labor_level_3,
                    r.pay_code.value,
                    r.source.value,
                    r.terminal_id or "",
                    str(r.edited).lower(),
                    r.edit_user or "",
                    r.edit_reason or "",
                    r.override or "",
                ]
            )


def _write_daily_totals(rows, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "person_number",
                "work_date",
                "pay_code",
                "hours",
                "job",
                "labor_level_1",
                "labor_level_2",
                "labor_level_3",
                "shift_count",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.person_number,
                    r.work_date.isoformat(),
                    r.pay_code.value,
                    f"{r.hours:.2f}",
                    r.job,
                    r.labor_level_1,
                    r.labor_level_2,
                    r.labor_level_3,
                    r.shift_count,
                ]
            )


def _write_pay_period_summary(rows, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "person_number",
                "pay_period_start",
                "pay_period_end",
                "regular_hours",
                "overtime_hours",
                "doubletime_hours",
                "holiday_hours",
                "sick_hours",
                "pto_hours",
                "shift_count",
                "missed_punch_count",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.person_number,
                    r.pay_period_start.isoformat(),
                    r.pay_period_end.isoformat(),
                    f"{r.regular_hours:.2f}",
                    f"{r.overtime_hours:.2f}",
                    f"{r.doubletime_hours:.2f}",
                    f"{r.holiday_hours:.2f}",
                    f"{r.sick_hours:.2f}",
                    f"{r.pto_hours:.2f}",
                    r.shift_count,
                    r.missed_punch_count,
                ]
            )


def generate_and_write(
    end_date: date | None = None,
    days: int = DEFAULT_DAYS,
    seed: int = 42,
    out_dir: Path | None = None,
) -> dict[str, int]:
    """Generate the three Kronos CSVs and write them to ``out_dir``.

    Reusable entry point so ``seed_dev_data.py`` can call this directly
    (rather than shelling out) to keep the dummy time-clock data fresh
    against today's date on every seed run.

    ``end_date`` defaults to ``date.today()``. ``out_dir`` defaults to
    ``DEFAULT_ARTIFACTS_DIR``. Returns a small summary dict for logging.
    """
    if end_date is None:
        end_date = date.today()
    if out_dir is None:
        out_dir = DEFAULT_ARTIFACTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    start_date = end_date - timedelta(days=days - 1)
    print(
        f"Generating Kronos punches for {start_date.isoformat()} to "
        f"{end_date.isoformat()} (seed={seed})"
    )

    staff = _staff_seeds()
    punches = generate_punches(staff, start_date, end_date, seed=seed)
    print(f"  staff: {len(staff)}  punches: {len(punches):,}")

    # Pay periods are biweekly anchored to the seed's known Monday.
    summaries = []
    daily_totals_all = []

    period_start = _floor_to_cycle(start_date)
    while period_start <= end_date:
        period_end = period_start + timedelta(days=PAY_PERIOD_LENGTH_DAYS - 1)
        period_punches = [
            p
            for p in punches
            if period_start
            <= p.punch_datetime.date()
            <= period_end + timedelta(days=1)  # NIGHT shifts cross the boundary
        ]
        totals, summary = aggregate(period_punches, period_start, period_end)
        # Drop totals outside the window (NIGHT shift ends bleed in)
        totals = [t for t in totals if period_start <= t.work_date <= period_end]
        daily_totals_all.extend(totals)
        summaries.extend(summary)
        period_start = period_end + timedelta(days=1)

    print(
        f"  daily totals: {len(daily_totals_all):,}  "
        f"pay period rows: {len(summaries):,}"
    )

    _write_punches(punches, out_dir / PUNCHES_FILE)
    _write_daily_totals(daily_totals_all, out_dir / DAILY_TOTALS_FILE)
    _write_pay_period_summary(summaries, out_dir / PAY_PERIOD_FILE)
    print(f"Wrote 3 files to {out_dir}")

    return {
        "punches": len(punches),
        "daily_totals": len(daily_totals_all),
        "pay_period_rows": len(summaries),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        default=None,
        help="End date of the punch window (inclusive). Default: today.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"Number of days of history to generate. Default: {DEFAULT_DAYS}",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic RNG seed. Default: 42",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_ARTIFACTS_DIR,
        help=f"Output directory. Default: {DEFAULT_ARTIFACTS_DIR}",
    )
    args = parser.parse_args()
    generate_and_write(
        end_date=args.end,
        days=args.days,
        seed=args.seed,
        out_dir=args.out_dir,
    )


def _floor_to_cycle(d: date) -> date:
    anchor = date(2026, 3, 30)
    days_since = (d - anchor).days
    cycle_offset = (days_since // 14) * 14
    return anchor + timedelta(days=cycle_offset)


if __name__ == "__main__":
    main()
