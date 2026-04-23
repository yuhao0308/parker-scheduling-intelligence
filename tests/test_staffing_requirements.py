from __future__ import annotations

from app.models.unit import ShiftLabel, Unit, UnitTypology
from app.services.staffing_requirements import slot_requirements


def test_explicit_calendar_requirement_preserves_total_and_bucket_mix():
    unit = Unit(
        unit_id="U-SA1",
        name="Subacute Unit 1",
        typology=UnitTypology.SUBACUTE,
        required_ratio=3.5,
        is_active=True,
    )

    req = slot_requirements(unit, ShiftLabel.DAY)

    assert req.total == 5
    assert req.licensed == 2
    assert req.certified == 3


def test_unknown_unit_falls_back_to_required_ratio_pattern():
    unit = Unit(
        unit_id="TEST-LT9",
        name="Test Long-Term",
        typology=UnitTypology.LT,
        required_ratio=2.2,
        is_active=True,
    )

    day = slot_requirements(unit, ShiftLabel.DAY)
    night = slot_requirements(unit, ShiftLabel.NIGHT)

    assert day.total == 4
    assert day.licensed == 1
    assert day.certified == 3
    assert night.total == 3
    assert night.licensed == 1
    assert night.certified == 2
