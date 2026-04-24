"""Shared staffing requirements for schedule generation and calendar demand."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from app.models.unit import ShiftLabel, Unit, UnitTypology

# Current United Hebrew demo demand shown in the monthly calendar and Auto-Gen panel.
# Values represent total people required for the unit/shift, not just one bucket.
UNIT_SHIFT_REQUIRED: dict[str, dict[str, int]] = {
    "U-SA1": {"DAY": 5, "EVENING": 5, "NIGHT": 4},
    "U-SA2": {"DAY": 5, "EVENING": 5, "NIGHT": 4},
    "U-SA3": {"DAY": 4, "EVENING": 4, "NIGHT": 3},
    "U-SA4": {"DAY": 4, "EVENING": 4, "NIGHT": 3},
    "U-LT1": {"DAY": 5, "EVENING": 5, "NIGHT": 4},
    "U-LT2": {"DAY": 5, "EVENING": 5, "NIGHT": 4},
    "U-LT3": {"DAY": 4, "EVENING": 4, "NIGHT": 3},
    "U-LT4": {"DAY": 4, "EVENING": 4, "NIGHT": 3},
    "U-LT5": {"DAY": 3, "EVENING": 3, "NIGHT": 2},
}

DEFAULT_REQUIRED = {"DAY": 4, "EVENING": 4, "NIGHT": 3}


@dataclass(frozen=True)
class SlotRequirements:
    total: int
    licensed: int
    certified: int


def _shift_key(shift_label: ShiftLabel | str) -> str:
    return shift_label.value if hasattr(shift_label, "value") else str(shift_label)


def _typology(unit: Unit) -> UnitTypology:
    value = unit.typology.value if hasattr(unit.typology, "value") else unit.typology
    return UnitTypology(value)


def licensed_staff_required(unit: Unit) -> int:
    return 2 if _typology(unit) == UnitTypology.SUBACUTE else 1


def _derived_certified_required(unit: Unit, shift_label: ShiftLabel | str) -> int | None:
    if unit.required_ratio is None:
        return None

    # Night shifts can run one certified staff lighter than day/evening while
    # preserving the United Hebrew staffing pattern used in the demo calendar.
    base = max(0, ceil(float(unit.required_ratio)))
    if _shift_key(shift_label) == "NIGHT":
        return max(0, base - 1)
    return base


def slot_requirements(unit: Unit, shift_label: ShiftLabel | str) -> SlotRequirements:
    key = _shift_key(shift_label)
    licensed = licensed_staff_required(unit)

    explicit_total = UNIT_SHIFT_REQUIRED.get(unit.unit_id, {}).get(key)
    if explicit_total is not None:
        total = explicit_total
    else:
        derived_certified = _derived_certified_required(unit, key)
        if derived_certified is not None:
            total = licensed + derived_certified
        else:
            total = DEFAULT_REQUIRED[key]

    certified = max(0, total - licensed)
    return SlotRequirements(total=total, licensed=licensed, certified=certified)
