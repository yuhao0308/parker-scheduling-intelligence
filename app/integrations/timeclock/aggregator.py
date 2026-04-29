"""Aggregation: raw punches -> daily totals -> biweekly summary -> HoursLedger.

This is the layer that converts the time clock vendor's view of reality
into the internal model the scoring engine consumes. It implements the
healthcare-payroll conventions that catch naive aggregations:

  - 7-minute rounding rule: punches within +/- 7 minutes of a quarter hour
    snap to that quarter hour (Kronos default, matches FLSA "de minimis" caps)
  - Meal break handling: explicit MEAL_START/MEAL_END pairs are unpaid; if
    they're missing on a shift > 6 hours we apply the auto-deduct policy
  - Missed punch closure: an unmatched IN with no matching OUT before the
    next shift gets auto-closed with override=AUTO_OUT, and the day is
    flagged for manager review
  - Mid-shift transfers: a TRANSFER punch splits the shift across two
    daily-totals rows (one per cost center) without breaking continuity
  - 8/80 overtime: NJ healthcare OT regime — OT after 8/day OR 80/biweek,
    whichever produces more OT hours for the employee (governs RN dual-track)

The aggregator is pure (no I/O); it takes already-fetched punch records and
returns derived totals. The CLI script and ingestion endpoints handle I/O.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.integrations.timeclock.kronos_schema import (
    KronosDailyTotal,
    KronosPayPeriodSummary,
    KronosPunchRecord,
    PayCode,
    PunchDirection,
    PunchSource,
    PunchType,
)
from app.services.shift_utils import get_operational_day

# Quarter-hour rounding window — punches within this many minutes of a
# quarter hour snap to it. 7 minutes is the Kronos default and the FLSA
# "de minimis" cap.
ROUND_WINDOW_MIN = 7

# Auto-deduct policy: if a shift > 6 hours has no explicit meal punches,
# Kronos deducts this many minutes as unpaid meal time.
AUTO_MEAL_DEDUCT_MIN = 30
AUTO_MEAL_THRESHOLD_HOURS = 6.0

# 8/80 overtime thresholds (NJ healthcare). Hours beyond either threshold
# in the relevant period are paid at OT (1.5x).
DAILY_OT_THRESHOLD = 8.0
BIWEEKLY_OT_THRESHOLD = 80.0

# Maximum gap between an IN punch and a paired OUT before the engine treats
# the IN as orphaned. A back-to-back double in LTC runs ~16h 15m on the
# clock (two 8h shifts plus a single 30-min meal), so 18h gives headroom for
# rounding and still catches real "forgot to clock out yesterday" orphans.
MAX_OPEN_PUNCH_HOURS = 18.0


@dataclass(frozen=True)
class ShiftSegment:
    """One contiguous block of clock-in time, between two punches.

    A normal shift is one segment. A shift with a mid-shift transfer becomes
    two segments (one per cost center). An auto-closed shift carries
    ``auto_closed=True`` so downstream reports can flag it.
    """

    person_number: str
    person_name: str
    start: datetime
    end: datetime
    labor_level_1: str
    labor_level_2: str
    labor_level_3: str
    auto_closed: bool = False
    edited: bool = False

    @property
    def duration_hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0

    @property
    def operational_day(self) -> date:
        return get_operational_day(self.start)


def round_to_quarter_hour(dt: datetime) -> datetime:
    """Snap a punch to the nearest quarter hour if within ROUND_WINDOW_MIN.

    Punches outside the window keep their original time — Kronos only rounds
    "near misses" so an employee who clocks in 30 minutes early gets paid
    from when they actually clocked in (subject to override rules).
    """
    minute = dt.minute
    nearest_quarter = round(minute / 15) * 15
    delta = abs(minute - nearest_quarter)
    if delta > ROUND_WINDOW_MIN:
        return dt.replace(second=0, microsecond=0)

    if nearest_quarter == 60:
        return dt.replace(second=0, microsecond=0, minute=0) + timedelta(hours=1)
    return dt.replace(second=0, microsecond=0, minute=nearest_quarter)


def pair_punches_into_segments(
    punches: list[KronosPunchRecord],
) -> tuple[list[ShiftSegment], list[KronosPunchRecord]]:
    """Pair IN punches with OUT punches into shift segments.

    Returns ``(segments, orphaned_ins)``. Orphaned INs (no matching OUT
    within MAX_OPEN_PUNCH_HOURS) are returned separately so the caller
    decides whether to drop them or apply an auto-out.

    Mid-shift TRANSFER punches close the current segment and open a new one
    at the same instant with the new cost center.
    """
    by_employee: dict[str, list[KronosPunchRecord]] = defaultdict(list)
    for p in punches:
        by_employee[p.person_number].append(p)

    segments: list[ShiftSegment] = []
    orphans: list[KronosPunchRecord] = []

    for person_number, plist in by_employee.items():
        plist.sort(key=lambda p: p.punch_datetime)
        open_in: KronosPunchRecord | None = None

        for p in plist:
            if p.punch_type in (PunchType.MEAL_START, PunchType.MEAL_END):
                # Meal punches are not segment delimiters; they're handled
                # in apply_meal_deduction at the segment level.
                continue

            if p.direction == PunchDirection.IN:
                if open_in is not None:
                    # Two consecutive INs without an OUT — treat the prior
                    # IN as orphaned.
                    orphans.append(open_in)
                open_in = p
                continue

            # OUT or TRANSFER (a TRANSFER carries direction=OUT for the
            # closing leg and is followed by a fresh IN).
            if open_in is None:
                # OUT with no prior IN — discard; the matching IN is in
                # the previous fetch window.
                continue

            duration = (p.punch_datetime - open_in.punch_datetime).total_seconds() / 3600.0
            if duration > MAX_OPEN_PUNCH_HOURS:
                orphans.append(open_in)
                open_in = None
                continue

            seg_start = round_to_quarter_hour(open_in.punch_datetime)
            seg_end = round_to_quarter_hour(p.punch_datetime)
            segments.append(
                ShiftSegment(
                    person_number=person_number,
                    person_name=open_in.person_name,
                    start=seg_start,
                    end=seg_end,
                    labor_level_1=open_in.labor_level_1,
                    labor_level_2=open_in.labor_level_2,
                    labor_level_3=open_in.labor_level_3,
                    auto_closed=p.override == "AUTO_OUT",
                    edited=open_in.edited or p.edited,
                )
            )
            open_in = None

        if open_in is not None:
            orphans.append(open_in)

    segments.sort(key=lambda s: (s.person_number, s.start))
    return segments, orphans


def apply_meal_deduction(
    segments: list[ShiftSegment],
    explicit_meals: dict[tuple[str, date], float],
) -> list[ShiftSegment]:
    """Subtract unpaid meal time from segments long enough to require it.

    ``explicit_meals`` maps (person_number, operational_day) to total minutes
    the employee punched out for meals. If absent and the shift is over the
    auto-deduct threshold, AUTO_MEAL_DEDUCT_MIN is subtracted off the end of
    the segment. Shifts at or below the threshold are paid through.
    """
    out: list[ShiftSegment] = []
    for seg in segments:
        key = (seg.person_number, seg.operational_day)
        if key in explicit_meals:
            deduct_min = explicit_meals[key]
        elif seg.duration_hours > AUTO_MEAL_THRESHOLD_HOURS:
            deduct_min = AUTO_MEAL_DEDUCT_MIN
        else:
            deduct_min = 0

        if deduct_min == 0:
            out.append(seg)
            continue

        new_end = seg.end - timedelta(minutes=deduct_min)
        if new_end <= seg.start:
            # Pathological case: meal longer than shift. Drop the segment;
            # this would be a data quality alert in production.
            continue
        out.append(
            ShiftSegment(
                person_number=seg.person_number,
                person_name=seg.person_name,
                start=seg.start,
                end=new_end,
                labor_level_1=seg.labor_level_1,
                labor_level_2=seg.labor_level_2,
                labor_level_3=seg.labor_level_3,
                auto_closed=seg.auto_closed,
                edited=seg.edited,
            )
        )
    return out


def collect_explicit_meals(
    punches: list[KronosPunchRecord],
) -> dict[tuple[str, date], float]:
    """Sum up explicit meal punch durations per employee per operational day."""
    meals: dict[tuple[str, date], float] = defaultdict(float)
    by_emp: dict[str, list[KronosPunchRecord]] = defaultdict(list)
    for p in punches:
        if p.punch_type in (PunchType.MEAL_START, PunchType.MEAL_END):
            by_emp[p.person_number].append(p)

    for person_number, plist in by_emp.items():
        plist.sort(key=lambda p: p.punch_datetime)
        open_meal: KronosPunchRecord | None = None
        for p in plist:
            if p.punch_type == PunchType.MEAL_START:
                open_meal = p
            elif p.punch_type == PunchType.MEAL_END and open_meal is not None:
                minutes = (
                    p.punch_datetime - open_meal.punch_datetime
                ).total_seconds() / 60.0
                op_day = get_operational_day(open_meal.punch_datetime)
                meals[(person_number, op_day)] += minutes
                open_meal = None
    return meals


def segments_to_daily_totals(
    segments: list[ShiftSegment],
) -> list[KronosDailyTotal]:
    """Roll up segments into one row per (employee, operational_day, paycode, job).

    Hours are rounded to the nearest quarter hour. The 8/day OT split is
    applied here; the biweekly 8/80 split is applied in the pay-period
    summary because it requires cross-day knowledge.
    """
    grouped: dict[
        tuple[str, date, str, str, str], list[ShiftSegment]
    ] = defaultdict(list)
    for seg in segments:
        key = (
            seg.person_number,
            seg.operational_day,
            seg.labor_level_1,
            seg.labor_level_2,
            seg.labor_level_3,
        )
        grouped[key].append(seg)

    # Per-employee per-operational-day cumulative hours, used to apply the
    # daily OT threshold across multiple cost centers.
    daily_running: dict[tuple[str, date], float] = defaultdict(float)
    out: list[KronosDailyTotal] = []

    # Process in deterministic order so the daily threshold lands on the
    # earliest segments first.
    for key in sorted(grouped.keys(), key=lambda k: (k[0], k[1], k[3])):
        person_number, op_day, ll1, ll2, ll3 = key
        segs = grouped[key]
        total_hours = round(sum(s.duration_hours for s in segs) * 4) / 4
        if total_hours == 0:
            continue

        running = daily_running[(person_number, op_day)]
        reg_room = max(0.0, DAILY_OT_THRESHOLD - running)
        reg_part = min(total_hours, reg_room)
        ot_part = total_hours - reg_part
        daily_running[(person_number, op_day)] = running + total_hours

        job = f"{ll1}/{ll2}/{ll3}"
        if reg_part > 0:
            out.append(
                KronosDailyTotal(
                    person_number=person_number,
                    work_date=op_day,
                    pay_code=PayCode.REG,
                    hours=round(reg_part * 4) / 4,
                    job=job,
                    labor_level_1=ll1,
                    labor_level_2=ll2,
                    labor_level_3=ll3,
                    shift_count=len(segs),
                )
            )
        if ot_part > 0:
            out.append(
                KronosDailyTotal(
                    person_number=person_number,
                    work_date=op_day,
                    pay_code=PayCode.OT,
                    hours=round(ot_part * 4) / 4,
                    job=job,
                    labor_level_1=ll1,
                    labor_level_2=ll2,
                    labor_level_3=ll3,
                    shift_count=0,  # OT row borrows the shift from the REG row
                )
            )

    return out


def daily_totals_to_pay_period_summary(
    totals: list[KronosDailyTotal],
    period_start: date,
    period_end: date,
    missed_punch_counts: dict[str, int] | None = None,
) -> list[KronosPayPeriodSummary]:
    """Roll daily totals into biweekly summaries with 8/80 OT applied.

    NJ healthcare uses 8/80: hours beyond 8 in a day OR 80 in the biweekly
    cycle are OT, whichever yields more OT hours. Daily OT was already
    applied in segments_to_daily_totals; here we apply the biweekly cap
    on top, promoting REG hours to OT when the running total exceeds 80.
    """
    missed = missed_punch_counts or {}
    by_emp: dict[str, list[KronosDailyTotal]] = defaultdict(list)
    for t in totals:
        if period_start <= t.work_date <= period_end:
            by_emp[t.person_number].append(t)

    out: list[KronosPayPeriodSummary] = []
    for person_number, rows in by_emp.items():
        reg = sum(r.hours for r in rows if r.pay_code == PayCode.REG)
        ot = sum(r.hours for r in rows if r.pay_code == PayCode.OT)
        dt = sum(r.hours for r in rows if r.pay_code == PayCode.DT)
        hol = sum(r.hours for r in rows if r.pay_code == PayCode.HOL)
        sick = sum(r.hours for r in rows if r.pay_code == PayCode.SICK)
        pto = sum(r.hours for r in rows if r.pay_code == PayCode.PTO)

        # Biweekly 8/80: promote REG hours over 80 to OT.
        if reg > BIWEEKLY_OT_THRESHOLD:
            promote = reg - BIWEEKLY_OT_THRESHOLD
            reg = BIWEEKLY_OT_THRESHOLD
            ot += promote

        shift_count = sum(r.shift_count for r in rows)
        out.append(
            KronosPayPeriodSummary(
                person_number=person_number,
                pay_period_start=period_start,
                pay_period_end=period_end,
                regular_hours=round(reg * 4) / 4,
                overtime_hours=round(ot * 4) / 4,
                doubletime_hours=round(dt * 4) / 4,
                holiday_hours=round(hol * 4) / 4,
                sick_hours=round(sick * 4) / 4,
                pto_hours=round(pto * 4) / 4,
                shift_count=shift_count,
                missed_punch_count=missed.get(person_number, 0),
            )
        )
    out.sort(key=lambda s: s.person_number)
    return out


def aggregate(
    punches: list[KronosPunchRecord],
    period_start: date,
    period_end: date,
) -> tuple[list[KronosDailyTotal], list[KronosPayPeriodSummary]]:
    """Full pipeline: punches -> daily totals -> pay period summary.

    Convenience entry point used by the generator and ingestion endpoints.
    The aggregator is pure — pass it the raw punches and it returns derived
    totals; persistence happens at the caller.
    """
    segments, orphans = pair_punches_into_segments(punches)
    if orphans:
        # Apply auto-out to orphans: close them at +8h with override.
        synthesized: list[KronosPunchRecord] = []
        for o in orphans:
            synthesized.append(
                KronosPunchRecord(
                    person_number=o.person_number,
                    person_name=o.person_name,
                    punch_datetime=o.punch_datetime + timedelta(hours=8, minutes=15),
                    direction=PunchDirection.OUT,
                    punch_type=PunchType.NORMAL,
                    labor_level_1=o.labor_level_1,
                    labor_level_2=o.labor_level_2,
                    labor_level_3=o.labor_level_3,
                    pay_code=o.pay_code,
                    source=PunchSource.AUTO,
                    edited=True,
                    edit_user="system",
                    edit_reason="Auto-closed missing punch",
                    override="AUTO_OUT",
                )
            )
        segments, _ = pair_punches_into_segments(punches + synthesized)

    explicit_meals = collect_explicit_meals(punches)
    segments = apply_meal_deduction(segments, explicit_meals)

    totals = segments_to_daily_totals(segments)

    # Count missed-punch-driven edits per employee for audit flagging.
    missed_counts: dict[str, int] = defaultdict(int)
    for seg in segments:
        if seg.auto_closed and period_start <= seg.operational_day <= period_end:
            missed_counts[seg.person_number] += 1

    summary = daily_totals_to_pay_period_summary(
        totals, period_start, period_end, dict(missed_counts)
    )
    return totals, summary
