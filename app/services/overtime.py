"""Overtime headroom calculator.

Two distinct OT tracks:
  CNA/PCT/LPN: Weekly OT after 37.5 hours
  RN:          Dual-track — daily OT (2nd shift in operational day) AND
               biweekly OT (11th shift in 14-day pay cycle)

The returned headroom is normalized to 0.0–1.0 for scoring.
"""

from __future__ import annotations

from datetime import date

from app.schemas.common import LICENSED_ROLES, LicenseType, ShiftLabel
from app.services.shift_utils import SHIFT_DURATION_HOURS, is_rn_daily_ot

# Overtime thresholds
WEEKLY_OT_THRESHOLD_HOURS = 37.5
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
    """CNA/PCT/LPN: simple weekly OT after 37.5 hours."""
    hours_after_shift = hours_this_cycle + SHIFT_DURATION_HOURS
    would_trigger = hours_after_shift > WEEKLY_OT_THRESHOLD_HOURS

    headroom_hours = max(0.0, WEEKLY_OT_THRESHOLD_HOURS - hours_this_cycle)
    normalized = min(1.0, headroom_hours / WEEKLY_OT_THRESHOLD_HOURS)
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
