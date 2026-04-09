"""Shift time math for Parker's operational day and shift windows.

Parker's operational day starts at 11PM (23:00), not midnight.
The NIGHT shift (23:00–07:15) is the FIRST shift of the operational day.

Shift structure:
  NIGHT:   23:00 – 07:15
  DAY:     07:00 – 15:15
  EVENING: 15:00 – 23:15

There is a 15-minute overlap between shifts for handoff.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.schemas.common import ShiftLabel

# Parker's operational day boundary
OPERATIONAL_DAY_START = time(23, 0)

# Shift windows
SHIFT_WINDOWS: dict[ShiftLabel, tuple[time, time]] = {
    ShiftLabel.NIGHT: (time(23, 0), time(7, 15)),
    ShiftLabel.DAY: (time(7, 0), time(15, 15)),
    ShiftLabel.EVENING: (time(15, 0), time(23, 15)),
}

# Standard shift duration in hours (8h 15m)
SHIFT_DURATION_HOURS = 8.25


def get_operational_day(dt: datetime) -> date:
    """Return the operational day for a given datetime.

    The operational day starts at 23:00. Datetimes from 23:00 on day X
    through 22:59 on day X+1 belong to operational day X+1.

    Examples:
      2026-04-08 23:00 → operational day 2026-04-09 (night shift starts new day)
      2026-04-09 06:00 → operational day 2026-04-09 (still in night shift)
      2026-04-09 08:00 → operational day 2026-04-09 (day shift)
      2026-04-09 22:59 → operational day 2026-04-09 (evening shift ending)
    """
    if dt.time() >= OPERATIONAL_DAY_START:
        return (dt + timedelta(days=1)).date()
    return dt.date()


def get_shift_date(shift_date: date, shift_label: ShiftLabel) -> date:
    """Return the operational day for a shift given its calendar date and label.

    The NIGHT shift starting at 23:00 on calendar date X belongs to
    operational day X+1. DAY and EVENING shifts belong to their calendar date.
    """
    if shift_label == ShiftLabel.NIGHT:
        return shift_date + timedelta(days=1)
    return shift_date


def get_shift_window(label: ShiftLabel) -> tuple[time, time]:
    """Return (start_time, end_time) for the given shift."""
    return SHIFT_WINDOWS[label]


def shift_to_datetime_range(
    shift_date: date, shift_label: ShiftLabel
) -> tuple[datetime, datetime]:
    """Convert a shift date + label to start/end datetimes.

    The shift_date is the calendar date when the shift starts.
    For NIGHT shifts, start is at 23:00 on shift_date and end is 07:15 on shift_date+1.
    """
    start_time, end_time = SHIFT_WINDOWS[shift_label]
    start_dt = datetime.combine(shift_date, start_time)

    if shift_label == ShiftLabel.NIGHT:
        end_dt = datetime.combine(shift_date + timedelta(days=1), end_time)
    else:
        end_dt = datetime.combine(shift_date, end_time)

    return start_dt, end_dt


def count_shifts_in_operational_day(
    employee_shifts: list[tuple[date, ShiftLabel]],
    target_date: date,
    target_label: ShiftLabel,
) -> int:
    """Count how many shifts the employee already has in the operational day
    that contains the target shift.

    This is used for:
    - Hard filter: max 2 shifts per 24h operational window
    - RN daily OT: second shift in same operational day triggers OT
    """
    target_op_day = get_shift_date(target_date, target_label)

    count = 0
    for s_date, s_label in employee_shifts:
        if get_shift_date(s_date, s_label) == target_op_day:
            count += 1
    return count


def is_rn_daily_ot(
    employee_shifts: list[tuple[date, ShiftLabel]],
    target_date: date,
    target_label: ShiftLabel,
) -> bool:
    """Return True if adding this shift would be the 2nd+ in the same operational day.

    For RNs, a second shift within the same 11PM–11PM boundary triggers daily OT.
    """
    existing = count_shifts_in_operational_day(employee_shifts, target_date, target_label)
    return existing >= 1
