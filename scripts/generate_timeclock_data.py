"""Materialize Kronos-format dummy time clock CSVs to artifacts/timeclock/.

Generates 90 days of punch history for the seeded United Hebrew roster,
runs the aggregator to derive daily totals and biweekly summaries, and
writes all three layers to CSV. Output files are consumed by
``app.integrations.timeclock.source.CSVSource`` and the API/DB stub
variants behind the same interface.

Usage:
    python scripts/generate_timeclock_data.py
    python scripts/generate_timeclock_data.py --days 30 --seed 7
    python scripts/generate_timeclock_data.py --end 2026-04-28 --days 90
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

DEFAULT_END = date(2026, 4, 28)
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        default=DEFAULT_END,
        help="End date of the punch window (inclusive). Default: 2026-04-28",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help="Number of days of history to generate. Default: 90",
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

    args.out_dir.mkdir(parents=True, exist_ok=True)

    start_date = args.end - timedelta(days=args.days - 1)
    print(
        f"Generating Kronos punches for {start_date.isoformat()} to "
        f"{args.end.isoformat()} (seed={args.seed})"
    )

    staff = _staff_seeds()
    punches = generate_punches(staff, start_date, args.end, seed=args.seed)
    print(f"  staff: {len(staff)}  punches: {len(punches):,}")

    # Pay periods are biweekly anchored to the seed's known Monday.
    summaries = []
    daily_totals_all = []

    period_start = _floor_to_cycle(start_date)
    while period_start <= args.end:
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

    _write_punches(punches, args.out_dir / PUNCHES_FILE)
    _write_daily_totals(daily_totals_all, args.out_dir / DAILY_TOTALS_FILE)
    _write_pay_period_summary(summaries, args.out_dir / PAY_PERIOD_FILE)
    print(f"Wrote 3 files to {args.out_dir}")


def _floor_to_cycle(d: date) -> date:
    anchor = date(2026, 3, 30)
    days_since = (d - anchor).days
    cycle_offset = (days_since // 14) * 14
    return anchor + timedelta(days=cycle_offset)


if __name__ == "__main__":
    main()
