"""Overtime headroom calculator.

Two distinct OT tracks:
  CNA/PCT/LPN: Weekly OT after 37.5 hours. Headroom uses a piecewise soft-cap
               matching Sean's rule ("more than 20–25 hours overtime per week,
               then I would not call him"): full headroom up to 37.5h, linear
               decay through the OT band, zero beyond HIGH_OT_SOFT_CAP_HOURS.
  RN:          Dual-track — daily OT (2nd shift in operational day) AND
               biweekly OT (11th shift in 14-day pay cycle).

The returned headroom is normalized to 0.0–1.0 for scoring.
"""

from __future__ import annotations

from datetime import date

from app.schemas.common import LICENSED_ROLES, LicenseType, ShiftLabel
from app.services.shift_utils import SHIFT_DURATION_HOURS, is_rn_daily_ot

# Overtime thresholds
WEEKLY_OT_THRESHOLD_HOURS = 37.5
# Sean's soft cap: 25h of OT above straight time. Beyond this, "I would not call him."
HIGH_OT_SOFT_CAP_HOURS = WEEKLY_OT_THRESHOLD_HOURS + 25.0  # 62.5
BIWEEKLY_SHIFT_OT_THRESHOLD = 10  # 11th shift triggers OT


def calculate_ot_headroom(
    license_type: LicenseType,
    hours_this_cycle: float,
    shift_count_this_biweek: int,
    employee_shifts: list[tuple[date, ShiftLabel]],
    target_date: date,
    target_label: ShiftLabel,
) -> tuple[float, bool]:
    """Calculate overtime headroom for a candidate.

    Returns:
        (normalized_headroom, would_trigger_ot)
        - normalized_headroom: 0.0 (no headroom / already OT) to 1.0 (max headroom)
        - would_trigger_ot: True if accepting this shift triggers any OT track
    """
    if license_type == LicenseType.RN:
        return _rn_headroom(
            hours_this_cycle,
            shift_count_this_biweek,
            employee_shifts,
            target_date,
            target_label,
        )
    else:
        return _standard_headroom(hours_this_cycle)


def _standard_headroom(hours_this_cycle: float) -> tuple[float, bool]:
    """CNA/PCT/LPN: weekly OT after 37.5h, with a soft cap at +25h of OT.

    Headroom curve (Sean's rule):
      hours <= 37.5            -> 1.0 (straight time; no penalty)
      37.5 < hours <= 62.5     -> linear decay 1.0 -> 0.0 across the OT band
      hours > 62.5             -> 0.0 (don't call)

    `would_trigger_ot` still fires as soon as the shift pushes past 37.5h so
    the rationale text can call it out — but the score no longer cliffs.
    """
    hours_after_shift = hours_this_cycle + SHIFT_DURATION_HOURS
    would_trigger = hours_after_shift > WEEKLY_OT_THRESHOLD_HOURS

    if hours_this_cycle <= WEEKLY_OT_THRESHOLD_HOURS:
        normalized = 1.0
    elif hours_this_cycle >= HIGH_OT_SOFT_CAP_HOURS:
        normalized = 0.0
    else:
        ot_band = HIGH_OT_SOFT_CAP_HOURS - WEEKLY_OT_THRESHOLD_HOURS
        ot_used = hours_this_cycle - WEEKLY_OT_THRESHOLD_HOURS
        normalized = max(0.0, 1.0 - (ot_used / ot_band))

    return normalized, would_trigger


def _rn_headroom(
    hours_this_cycle: float,
    shift_count_this_biweek: int,
    employee_shifts: list[tuple[date, ShiftLabel]],
    target_date: date,
    target_label: ShiftLabel,
) -> tuple[float, bool]:
    """RN: dual-track OT evaluation.

    Track 1 — Daily OT: If this is the 2nd shift in the same operational day
              (11PM–11PM boundary), it's automatically OT.
    Track 2 — Biweekly OT: If this is the 11th shift in the 14-day pay cycle,
              it triggers OT.

    Returns the minimum headroom across both tracks.
    """
    # Track 1: Daily OT
    daily_ot = is_rn_daily_ot(employee_shifts, target_date, target_label)
    daily_headroom = 0.0 if daily_ot else 1.0

    # Track 2: Biweekly shift count
    shifts_remaining = BIWEEKLY_SHIFT_OT_THRESHOLD - shift_count_this_biweek
    biweekly_headroom = max(0.0, shifts_remaining / BIWEEKLY_SHIFT_OT_THRESHOLD)
    biweekly_ot = shift_count_this_biweek >= BIWEEKLY_SHIFT_OT_THRESHOLD

    # Combined: use the tighter constraint
    normalized = min(daily_headroom, biweekly_headroom)
    would_trigger = daily_ot or biweekly_ot

    return normalized, would_trigger
