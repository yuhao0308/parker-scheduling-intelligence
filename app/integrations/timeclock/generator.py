"""Synthetic Kronos punch data generator with deliberate edge cases.

Produces ~90 days of punch history for a roster of staff, in Kronos WIM
shape. The output is faithful enough that swapping in a real client extract
is a column-rename exercise.

The generator is deterministic — same seed in, same data out — so tests can
assert on specific punches without fixtures going stale.

EDGE CASES
==========

In addition to a clean baseline, the generator injects six deliberately
problematic employees so demos can show that downstream code handles real-
world messiness:

  1. **Late Clocker (CHRONIC_LATE_EMP)** — clocks in 8-12 minutes late on
     ~60% of shifts. Beyond the 7-min rounding window, so it accumulates
     real lost hours. Not enough to be a no-show; just steady tardiness.

  2. **Forgotten Punch (MISSED_PUNCH_EMP)** — fails to clock out on ~5% of
     shifts. The aggregator auto-closes these with override=AUTO_OUT, and
     the pay-period summary surfaces the count for HR review.

  3. **OT Skirter (OT_SKIRTER_EMP)** — engineered to land at 79.5h biweekly
     (just under the 80h OT threshold). Demonstrates that workload signals
     should flag this pattern even though no OT is actually paid.

  4. **Worked Through Meal (NO_MEAL_EMP)** — never punches for meals despite
     8h+ shifts. Triggers AUTO_MEAL_DEDUCT — i.e., gets paid less than they
     worked. A common LTC labor-relations issue.

  5. **Floater (FLOATER_EMP)** — ~30% of shifts include a mid-shift TRANSFER
     to a different unit. Tests the aggregator's split-segment logic.

  6. **Doubles (DOUBLES_EMP)** — picks up back-to-back shifts ~25% of the
     time, producing daily totals that exceed 8h and trigger daily OT. The
     scoring engine should detect this fatigue signal.

The edge case employee IDs are exposed as module constants so tests can
assert against them without coupling to roster line numbers.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable

from app.integrations.timeclock.kronos_schema import (
    KronosPunchRecord,
    PayCode,
    PunchDirection,
    PunchSource,
    PunchType,
)

FACILITY = "UNITED_HEBREW"

# Edge case employee IDs — picked from the seeded roster (see scripts/seed_dev_data.py).
CHRONIC_LATE_EMP = "CNA002"      # FT CNA on U-SA1
MISSED_PUNCH_EMP = "CNA008"      # FT CNA on U-LT1
OT_SKIRTER_EMP = "RN004"          # FT RN on U-SA3 — picks up extra shifts up to 79.5h
NO_MEAL_EMP = "CNA009"            # PT CNA on U-LT2
FLOATER_EMP = "CNA001"            # FT CNA on U-SA1, cross-trained U-SA2/U-LT1
DOUBLES_EMP = "CNA005"            # PER_DIEM CNA — naturally picks up extras

EDGE_CASE_EMPLOYEES = frozenset(
    {
        CHRONIC_LATE_EMP,
        MISSED_PUNCH_EMP,
        OT_SKIRTER_EMP,
        NO_MEAL_EMP,
        FLOATER_EMP,
        DOUBLES_EMP,
    }
)

# Standard shift windows from app.services.shift_utils — duplicated here as
# tuples so the generator doesn't need a ShiftLabel enum import (Kronos
# doesn't think in our shift labels; it only sees punch times).
SHIFT_WINDOWS: dict[str, tuple[time, time]] = {
    "DAY": (time(7, 0), time(15, 15)),
    "EVENING": (time(15, 0), time(23, 15)),
    "NIGHT": (time(23, 0), time(7, 15)),
}


@dataclass
class StaffSeed:
    """Just enough about an employee to generate plausible punches.

    The full StaffSyncRecord lives in the seed script; we re-derive the
    minimum here so the generator can run without DB access.
    """

    employee_id: str
    name: str
    license: str  # "RN" | "LPN" | "CNA" | "PCT"
    employment_class: str  # "FT" | "PT" | "PER_DIEM"
    home_unit_id: str
    cross_trained_units: list[str]


def _shifts_per_week(employment_class: str) -> int:
    """Target shift frequency by employment class.

    FT = 5 shifts/week (40h target with 8.25h shifts pushes them slightly
    over but biweekly OT cap keeps it in line). PT = 3, per-diem = 1-2.
    """
    return {"FT": 5, "PT": 3, "PER_DIEM": 2}.get(employment_class, 3)


def _shift_for_dow(seed: StaffSeed, work_date: date, rng: random.Random) -> str | None:
    """Decide whether this employee works on this date and which shift.

    Each employee has a stable shift archetype (DAY/EVENING/NIGHT) so the
    pattern looks realistic across the period — they don't bounce between
    shifts at random. Days off are sampled from a Bernoulli with mean tied
    to their employment class.
    """
    target = _shifts_per_week(seed.employment_class)
    # OT skirter is a known overpicker — schedules an extra shift on most
    # days, then the cap-at-79.5h check below stops them just before OT.
    if seed.employee_id == OT_SKIRTER_EMP:
        target = 6
    works_today = rng.random() < (target / 7.0)
    if not works_today:
        return None

    # The doubles employee is pinned to DAY so that back-to-back shifts
    # (DAY + EVENING) land on the same operational day — otherwise a NIGHT
    # primary would push the second shift across the 23:00 boundary into
    # a separate op day and the "double" wouldn't show up as such.
    if seed.employee_id == DOUBLES_EMP:
        return "DAY"

    # Stable archetype based on a hash of employee_id, so each employee
    # consistently works the same shift unless we deliberately flip them.
    archetype_idx = sum(ord(c) for c in seed.employee_id) % 3
    return ["DAY", "EVENING", "NIGHT"][archetype_idx]


def _labor_levels(seed: StaffSeed, unit_override: str | None = None) -> tuple[str, str, str]:
    unit = unit_override or seed.home_unit_id
    return FACILITY, unit, seed.license


def _shift_punch_times(
    work_date: date, shift_label: str
) -> tuple[datetime, datetime]:
    start_time, end_time = SHIFT_WINDOWS[shift_label]
    start_dt = datetime.combine(work_date, start_time)
    if shift_label == "NIGHT":
        end_dt = datetime.combine(work_date + timedelta(days=1), end_time)
    else:
        end_dt = datetime.combine(work_date, end_time)
    return start_dt, end_dt


def _jitter(scheduled: datetime, rng: random.Random, late_minutes: int = 0) -> datetime:
    """Add realistic punch noise around a scheduled time.

    Most employees clock in 1-3 minutes early or 0-3 minutes late, well
    inside the 7-minute rounding window so the actual paid time is the
    scheduled time. ``late_minutes`` lets specific employees (the chronic
    late case) push beyond the rounding window.
    """
    if late_minutes > 0:
        offset = rng.randint(late_minutes, late_minutes + 4)
    else:
        offset = rng.randint(-3, 3)
    return scheduled + timedelta(minutes=offset)


def _normal_punches(
    seed: StaffSeed,
    work_date: date,
    shift_label: str,
    rng: random.Random,
    *,
    in_late_minutes: int = 0,
    drop_out_punch: bool = False,
    skip_meal: bool = False,
    transfer_to: str | None = None,
    unit_override: str | None = None,
) -> list[KronosPunchRecord]:
    """Generate the punch sequence for one shift on one date.

    Returns the IN, optional MEAL_START/MEAL_END, optional TRANSFER pair,
    and OUT punches. ``drop_out_punch=True`` simulates a forgotten clock-out
    — the IN is emitted but no OUT, so the aggregator will auto-close.
    """
    sched_in, sched_out = _shift_punch_times(work_date, shift_label)
    ll1, ll2, ll3 = _labor_levels(seed, unit_override)

    actual_in = _jitter(sched_in, rng, late_minutes=in_late_minutes)
    actual_out = _jitter(sched_out, rng)

    punches: list[KronosPunchRecord] = []
    punches.append(
        KronosPunchRecord(
            person_number=seed.employee_id,
            person_name=seed.name,
            punch_datetime=actual_in,
            direction=PunchDirection.IN,
            punch_type=PunchType.NORMAL,
            labor_level_1=ll1,
            labor_level_2=ll2,
            labor_level_3=ll3,
            pay_code=PayCode.REG,
            source=rng.choice(
                [PunchSource.TERMINAL, PunchSource.TERMINAL, PunchSource.MOBILE]
            ),
            terminal_id=f"T-{ll2}-01",
        )
    )

    if not skip_meal:
        meal_start = actual_in + timedelta(hours=4, minutes=rng.randint(0, 60))
        meal_end = meal_start + timedelta(minutes=30)
        punches.append(
            KronosPunchRecord(
                person_number=seed.employee_id,
                person_name=seed.name,
                punch_datetime=meal_start,
                direction=PunchDirection.OUT,
                punch_type=PunchType.MEAL_START,
                labor_level_1=ll1,
                labor_level_2=ll2,
                labor_level_3=ll3,
                pay_code=PayCode.REG,
                source=PunchSource.TERMINAL,
                terminal_id=f"T-{ll2}-01",
            )
        )
        punches.append(
            KronosPunchRecord(
                person_number=seed.employee_id,
                person_name=seed.name,
                punch_datetime=meal_end,
                direction=PunchDirection.IN,
                punch_type=PunchType.MEAL_END,
                labor_level_1=ll1,
                labor_level_2=ll2,
                labor_level_3=ll3,
                pay_code=PayCode.REG,
                source=PunchSource.TERMINAL,
                terminal_id=f"T-{ll2}-01",
            )
        )

    if transfer_to is not None:
        # Mid-shift transfer: OUT of the current cost center then IN at the
        # new one. Real Kronos can do this as a single TRANSFER punch but
        # representing it as a pair makes the aggregator easier to reason
        # about and matches what manual exports often look like.
        midpoint = actual_in + (actual_out - actual_in) / 2
        punches.append(
            KronosPunchRecord(
                person_number=seed.employee_id,
                person_name=seed.name,
                punch_datetime=midpoint,
                direction=PunchDirection.OUT,
                punch_type=PunchType.TRANSFER,
                labor_level_1=ll1,
                labor_level_2=ll2,
                labor_level_3=ll3,
                pay_code=PayCode.REG,
                source=PunchSource.TERMINAL,
                terminal_id=f"T-{ll2}-01",
            )
        )
        punches.append(
            KronosPunchRecord(
                person_number=seed.employee_id,
                person_name=seed.name,
                punch_datetime=midpoint,
                direction=PunchDirection.IN,
                punch_type=PunchType.NORMAL,
                labor_level_1=ll1,
                labor_level_2=transfer_to,
                labor_level_3=ll3,
                pay_code=PayCode.REG,
                source=PunchSource.TERMINAL,
                terminal_id=f"T-{transfer_to}-01",
            )
        )

    if not drop_out_punch:
        out_unit = transfer_to or ll2
        punches.append(
            KronosPunchRecord(
                person_number=seed.employee_id,
                person_name=seed.name,
                punch_datetime=actual_out,
                direction=PunchDirection.OUT,
                punch_type=PunchType.NORMAL,
                labor_level_1=ll1,
                labor_level_2=out_unit,
                labor_level_3=ll3,
                pay_code=PayCode.REG,
                source=rng.choice(
                    [PunchSource.TERMINAL, PunchSource.TERMINAL, PunchSource.MOBILE]
                ),
                terminal_id=f"T-{out_unit}-01",
            )
        )
    return punches


def _generate_for_employee(
    seed: StaffSeed,
    start_date: date,
    end_date: date,
    rng: random.Random,
) -> list[KronosPunchRecord]:
    """Walk the date range and emit punches according to edge case rules."""
    punches: list[KronosPunchRecord] = []

    # OT skirter target: stop scheduling once they hit 79.5h in the current
    # biweekly cycle. Tracked per cycle keyed by Monday of the period start.
    ot_skirter_cycle_hours: dict[date, float] = {}

    cur = start_date
    while cur <= end_date:
        shift_label = _shift_for_dow(seed, cur, rng)
        if shift_label is None:
            cur += timedelta(days=1)
            continue

        in_late_minutes = 0
        drop_out_punch = False
        skip_meal = False
        transfer_to: str | None = None
        do_double = False

        if seed.employee_id == CHRONIC_LATE_EMP and rng.random() < 0.6:
            in_late_minutes = 8  # beyond rounding window
        if seed.employee_id == MISSED_PUNCH_EMP and rng.random() < 0.05:
            drop_out_punch = True
        if seed.employee_id == NO_MEAL_EMP:
            skip_meal = True
        if seed.employee_id == FLOATER_EMP and rng.random() < 0.3 and seed.cross_trained_units:
            transfer_to = rng.choice(seed.cross_trained_units)
        if seed.employee_id == DOUBLES_EMP and rng.random() < 0.25:
            do_double = True

        if seed.employee_id == OT_SKIRTER_EMP:
            cycle_start = _biweekly_cycle_start(cur)
            cycle_hours = ot_skirter_cycle_hours.get(cycle_start, 0.0)
            # Each shift contributes ~7.75h after meal deduct (8h15m - 30min).
            if cycle_hours + 7.75 > 79.5:
                cur += timedelta(days=1)
                continue
            ot_skirter_cycle_hours[cycle_start] = cycle_hours + 7.75

        punches.extend(
            _normal_punches(
                seed,
                cur,
                shift_label,
                rng,
                in_late_minutes=in_late_minutes,
                drop_out_punch=drop_out_punch,
                skip_meal=skip_meal,
                transfer_to=transfer_to,
            )
        )

        if do_double:
            # Doubles in real LTC don't punch out and back in — staff just
            # keep working. Model that as extending the OUT punch of the
            # last shift to cover the next one. We do this by replacing the
            # most recent OUT with one at the next shift's end time.
            archetypes = ["DAY", "EVENING", "NIGHT"]
            next_label = archetypes[(archetypes.index(shift_label) + 1) % 3]
            _, next_end = _shift_punch_times(cur, next_label)
            new_out = _jitter(next_end, rng)

            # Find and rewrite the last NORMAL OUT punch we just emitted.
            for i in range(len(punches) - 1, -1, -1):
                p = punches[i]
                if (
                    p.person_number == seed.employee_id
                    and p.direction == PunchDirection.OUT
                    and p.punch_type == PunchType.NORMAL
                ):
                    punches[i] = p.model_copy(update={"punch_datetime": new_out})
                    break

        cur += timedelta(days=1)

    return punches


def _biweekly_cycle_start(d: date) -> date:
    """Anchor biweekly cycles to Mondays divisible by 14 from epoch.

    Mirrors the seed's "RN cycle starts 2026-03-30" anchor — a Monday two
    weeks before April 13.
    """
    anchor = date(2026, 3, 30)  # known Monday cycle start
    days_since = (d - anchor).days
    cycle_offset = (days_since // 14) * 14
    return anchor + timedelta(days=cycle_offset)


def generate_punches(
    staff: Iterable[StaffSeed],
    start_date: date,
    end_date: date,
    seed: int = 42,
) -> list[KronosPunchRecord]:
    """Generate a deterministic punch dataset for the given roster and window."""
    out: list[KronosPunchRecord] = []
    for s in staff:
        # Per-employee RNG so adding an employee doesn't shift everyone
        # else's punches — keeps test fixtures stable.
        rng = random.Random(f"{seed}-{s.employee_id}")
        out.extend(_generate_for_employee(s, start_date, end_date, rng))

    out.sort(key=lambda p: (p.punch_datetime, p.person_number))
    return out
