from __future__ import annotations

from datetime import date
from typing import List, Optional

from app.schemas.callout import CalloutRequest
from app.schemas.common import LicenseType, ShiftLabel, UnitTypology
from app.schemas.schedule import GenerateScheduleRequest
from tests.scenarios.models import (
    HoursLedgerSeed,
    ScenarioAssertion,
    ScenarioSpec,
    ScenarioSetup,
    ScheduleEntrySeed,
    StaffSeed,
    UnitExclusionSeed,
    UnitSeed,
)


DEFAULT_STAFF_ZIPS_BY_UNIT = {
    "U-SA1": "11374",  # Rego Park (~0.8 mi from facility)
    "U-SA2": "11373",  # Elmhurst (~1.8 mi)
    "U-SA3": "11368",  # Corona (~1.7 mi)
    "U-SA4": "11372",  # Jackson Heights (~2.7 mi)
    "U-LT1": "11415",  # Kew Gardens (~1.4 mi)
    "U-LT2": "11418",  # Richmond Hill (~1.8 mi)
    "U-LT3": "11432",  # Jamaica (~2.9 mi)
    "U-LT4": "11367",  # Kew Gardens Hills (~1.5 mi)
    "U-LT5": "11004",  # Glen Oaks (~7.3 mi)
}


def _unit(unit_id: str, name: str, typology: UnitTypology) -> UnitSeed:
    return UnitSeed(unit_id=unit_id, name=name, typology=typology)


def _staff(
    employee_id: str,
    name: str,
    license: LicenseType,
    employment_class: str,
    home_unit_id: str,
    hire_date_: date,
    zip_code: Optional[str] = None,
    cross_trained_unit_ids: Optional[List[str]] = None,
) -> StaffSeed:
    return StaffSeed(
        employee_id=employee_id,
        name=name,
        license=license,
        employment_class=employment_class,
        zip_code=zip_code or DEFAULT_STAFF_ZIPS_BY_UNIT.get(home_unit_id, "11432"),
        home_unit_id=home_unit_id,
        hire_date=hire_date_,
        cross_trained_unit_ids=cross_trained_unit_ids or [],
    )


def _hours(
    employee_id: str,
    hours_this_cycle: float,
    shift_count_this_biweek: int = 0,
    cycle_start_date: date = date(2026, 4, 6),
) -> HoursLedgerSeed:
    return HoursLedgerSeed(
        employee_id=employee_id,
        cycle_start_date=cycle_start_date,
        hours_this_cycle=hours_this_cycle,
        shift_count_this_biweek=shift_count_this_biweek,
    )


def _entry(
    employee_id: str,
    unit_id: str,
    shift_date: date,
    shift_label: ShiftLabel,
) -> ScheduleEntrySeed:
    return ScheduleEntrySeed(
        employee_id=employee_id,
        unit_id=unit_id,
        shift_date=shift_date,
        shift_label=shift_label,
    )


def _assert(kind: str, description: str, **params) -> ScenarioAssertion:
    return ScenarioAssertion(kind=kind, description=description, params=params)


SCENARIOS: list[ScenarioSpec] = [
    ScenarioSpec(
        id="callout-subacute-best-fit",
        title="Subacute callout ranks the best clinically appropriate CNA first",
        business_rule=(
            "When a Subacute CNA calls out, the top replacement should favor lower "
            "overtime exposure and stronger Short-Term fit over weaker clinical matches."
        ),
        result_classification="pass",
        setup=ScenarioSetup(
            units=[
                _unit("U-SA1", "Subacute Unit 1", UnitTypology.SUBACUTE),
                _unit("U-LT1", "Long-Term Unit 1", UnitTypology.LT),
            ],
            staff=[
                _staff("CNA-CALL", "Callout CNA", LicenseType.CNA, "FT", "U-SA1", date(2020, 1, 1)),
                _staff("CNA-HOME", "Home Unit CNA", LicenseType.CNA, "FT", "U-SA1", date(2020, 6, 1)),
                _staff("CNA-FLOAT", "Float CNA", LicenseType.CNA, "FT", "U-LT1", date(2020, 6, 1)),
                _staff("CNA-OT", "Heavy OT CNA", LicenseType.CNA, "FT", "U-SA1", date(2020, 6, 1)),
            ],
            hours_ledgers=[
                _hours("CNA-HOME", 8.25),
                _hours("CNA-FLOAT", 8.25),
                _hours("CNA-OT", 45.0),
            ],
            schedule_entries=[
                _entry("CNA-CALL", "U-SA1", date(2026, 4, 14), ShiftLabel.DAY),
            ],
        ),
        action={
            "kind": "callout",
            "request": CalloutRequest(
                callout_employee_id="CNA-CALL",
                unit_id="U-SA1",
                shift_date=date(2026, 4, 14),
                shift_label=ShiftLabel.DAY,
            ),
        },
        expected_assertions=[
            _assert(
                "top_candidate_is",
                "The home-unit CNA with straight-time headroom should rank first.",
                employee_id="CNA-HOME",
            ),
        ],
    ),
    ScenarioSpec(
        id="callout-exclusion-enforced",
        title="Unit exclusions remove the otherwise best-fit candidate",
        business_rule=(
            "A staff member excluded from a unit must never appear in recommendations "
            "for that unit, even if they would otherwise rank first."
        ),
        result_classification="pass",
        setup=ScenarioSetup(
            units=[
                _unit("U-SA1", "Subacute Unit 1", UnitTypology.SUBACUTE),
                _unit("U-SA2", "Subacute Unit 2", UnitTypology.SUBACUTE),
            ],
            staff=[
                _staff("CNA-CALL", "Callout CNA", LicenseType.CNA, "FT", "U-SA1", date(2020, 1, 1)),
                _staff("CNA-BLOCKED", "Blocked CNA", LicenseType.CNA, "FT", "U-SA1", date(2020, 6, 1)),
                _staff(
                    "CNA-BACKUP",
                    "Backup CNA",
                    LicenseType.CNA,
                    "FT",
                    "U-SA2",
                    date(2020, 6, 1),
                    cross_trained_unit_ids=["U-SA1"],
                ),
            ],
            hours_ledgers=[
                _hours("CNA-BLOCKED", 8.25),
                _hours("CNA-BACKUP", 8.25),
            ],
            schedule_entries=[
                _entry("CNA-CALL", "U-SA1", date(2026, 4, 15), ShiftLabel.DAY),
            ],
            exclusions=[
                UnitExclusionSeed(
                    employee_id="CNA-BLOCKED",
                    unit_id="U-SA1",
                    reason="Do not assign to this unit",
                    effective_from=date(2026, 1, 1),
                    effective_until=None,
                )
            ],
        ),
        action={
            "kind": "callout",
            "request": CalloutRequest(
                callout_employee_id="CNA-CALL",
                unit_id="U-SA1",
                shift_date=date(2026, 4, 15),
                shift_label=ShiftLabel.DAY,
            ),
        },
        expected_assertions=[
            _assert(
                "candidate_not_present",
                "The excluded employee should not appear in the recommendation list.",
                employee_id="CNA-BLOCKED",
            ),
            _assert(
                "excluded_employee_never_assigned",
                "The excluded employee should be fully blocked for the target unit.",
                employee_id="CNA-BLOCKED",
            ),
            _assert(
                "top_candidate_is",
                "The cross-trained backup should become the top valid candidate.",
                employee_id="CNA-BACKUP",
            ),
        ],
    ),
    ScenarioSpec(
        id="callout-rest-window-enforced",
        title="Rest-window conflicts remove candidates with adjacent shifts",
        business_rule=(
            "A candidate who would exceed the allowed operational-day shift load must "
            "be filtered out before scoring."
        ),
        result_classification="pass",
        setup=ScenarioSetup(
            units=[_unit("U-SA1", "Subacute Unit 1", UnitTypology.SUBACUTE)],
            staff=[
                _staff("CNA-CALL", "Callout CNA", LicenseType.CNA, "FT", "U-SA1", date(2020, 1, 1)),
                _staff("CNA-REST", "Rest Conflict CNA", LicenseType.CNA, "FT", "U-SA1", date(2020, 6, 1)),
                _staff("CNA-SAFE", "Safe CNA", LicenseType.CNA, "FT", "U-SA1", date(2020, 6, 1)),
            ],
            schedule_entries=[
                _entry("CNA-CALL", "U-SA1", date(2026, 4, 10), ShiftLabel.EVENING),
                _entry("CNA-REST", "U-SA1", date(2026, 4, 9), ShiftLabel.NIGHT),
                _entry("CNA-REST", "U-SA1", date(2026, 4, 10), ShiftLabel.DAY),
            ],
        ),
        action={
            "kind": "callout",
            "request": CalloutRequest(
                callout_employee_id="CNA-CALL",
                unit_id="U-SA1",
                shift_date=date(2026, 4, 10),
                shift_label=ShiftLabel.EVENING,
            ),
        },
        expected_assertions=[
            _assert(
                "candidate_not_present",
                "The candidate with adjacent shifts should be filtered out.",
                employee_id="CNA-REST",
            ),
            _assert(
                "no_rest_window_violation",
                "No rest-window-violating candidate should remain in the ranked list.",
                employee_id="CNA-REST",
            ),
            _assert(
                "top_candidate_is",
                "The safe candidate should be the best remaining option.",
                employee_id="CNA-SAFE",
            ),
        ],
    ),
    ScenarioSpec(
        id="schedule-bucket-preference",
        title="Monthly generation keeps Subacute licensed and LT certified where possible",
        business_rule=(
            "With sufficient staffing, Subacute shifts should be filled from the "
            "licensed bucket and Long-Term shifts from the certified bucket."
        ),
        result_classification="pass",
        setup=ScenarioSetup(
            units=[
                _unit("U-SA1", "Subacute Unit 1", UnitTypology.SUBACUTE),
                _unit("U-LT1", "Long-Term Unit 1", UnitTypology.LT),
            ],
            staff=[
                *[
                    _staff(
                        f"RN-SA{i}",
                        f"Subacute RN {i}",
                        LicenseType.RN,
                        "FT",
                        "U-SA1",
                        date(2019, 1, i),
                    )
                    for i in range(1, 11)
                ],
                *[
                    _staff(
                        f"CNA-SA{i}",
                        f"Subacute CNA {i}",
                        LicenseType.CNA,
                        "FT",
                        "U-SA1",
                        date(2019, 2, i),
                    )
                    for i in range(1, 13)
                ],
                *[
                    _staff(
                        f"RN-LT{i}",
                        f"LT RN {i}",
                        LicenseType.RN,
                        "FT",
                        "U-LT1",
                        date(2019, 3, i),
                    )
                    for i in range(1, 6)
                ],
                *[
                    _staff(
                        f"CNA-LT{i}",
                        f"LT CNA {i}",
                        LicenseType.CNA,
                        "FT",
                        "U-LT1",
                        date(2019, 4, i),
                    )
                    for i in range(1, 19)
                ],
            ],
        ),
        action={
            "kind": "generate_schedule",
            "request": GenerateScheduleRequest(year=2026, month=4),
        },
        expected_assertions=[
            _assert(
                "scenario_label_is",
                "Sufficient staffing should produce the ideal scenario label.",
                value="ideal",
            ),
            _assert(
                "slot_assigned_license_in",
                "The first Subacute day shift should be covered by a licensed staff member.",
                unit_id="U-SA1",
                shift_date="2026-04-01",
                shift_label="DAY",
                licenses=["RN", "LPN"],
            ),
            _assert(
                "slot_assigned_license_in",
                "The first LT day shift should be covered by a certified staff member.",
                unit_id="U-LT1",
                shift_date="2026-04-01",
                shift_label="DAY",
                licenses=["CNA", "PCT"],
            ),
        ],
    ),
    ScenarioSpec(
        id="schedule-shortage-subacute-priority",
        title="Staff shortages preserve Subacute coverage ahead of LT",
        business_rule=(
            "When staffing is insufficient, higher-acuity Subacute coverage should be "
            "filled before lower-priority Long-Term coverage."
        ),
        result_classification="pass",
        setup=ScenarioSetup(
            units=[
                _unit("U-SA1", "Subacute Unit 1", UnitTypology.SUBACUTE),
                _unit("U-LT1", "Long-Term Unit 1", UnitTypology.LT),
            ],
            staff=[
                _staff("CNA-SHORT", "Shared CNA", LicenseType.CNA, "FT", "U-SA1", date(2020, 1, 1)),
            ],
        ),
        action={
            "kind": "generate_schedule",
            "request": GenerateScheduleRequest(year=2026, month=4),
        },
        expected_assertions=[
            _assert(
                "scenario_label_is",
                "Severe understaffing should show up in the scenario badge.",
                value="critical",
            ),
            _assert(
                "subacute_slots_filled_before_lt",
                "Subacute should retain at least as many filled slots as Long-Term under shortage.",
                subacute_unit_id="U-SA1",
                lt_unit_id="U-LT1",
            ),
        ],
    ),
    ScenarioSpec(
        id="minimum-hours-priority-gap",
        title="Minimum-hours-first fairness is still a known gap",
        business_rule=(
            "A full-time employee who needs hours should be prioritized ahead of a "
            "per-diem employee taking extra shifts, even when the per-diem worker has "
            "a stronger home-unit match."
        ),
        result_classification="gap",
        setup=ScenarioSetup(
            units=[
                _unit("U-LT1", "Long-Term Unit 1", UnitTypology.LT),
                _unit("U-LT2", "Long-Term Unit 2", UnitTypology.LT),
            ],
            staff=[
                _staff("CNA-CALL", "Callout CNA", LicenseType.CNA, "FT", "U-LT1", date(2020, 1, 1)),
                _staff(
                    "CNA-FT-NEEDS-HOURS",
                    "Needs Hours FT CNA",
                    LicenseType.CNA,
                    "FT",
                    "U-LT2",
                    date(2020, 6, 1),
                    zip_code="07030",
                ),
                _staff(
                    "CNA-PD-HOME",
                    "Home Unit Per Diem CNA",
                    LicenseType.CNA,
                    "PER_DIEM",
                    "U-LT1",
                    date(2020, 6, 1),
                ),
            ],
            hours_ledgers=[
                _hours("CNA-FT-NEEDS-HOURS", 0.0),
                _hours("CNA-PD-HOME", 16.5),
            ],
            schedule_entries=[
                _entry("CNA-CALL", "U-LT1", date(2026, 4, 16), ShiftLabel.DAY),
            ],
        ),
        action={
            "kind": "callout",
            "request": CalloutRequest(
                callout_employee_id="CNA-CALL",
                unit_id="U-LT1",
                shift_date=date(2026, 4, 16),
                shift_label=ShiftLabel.DAY,
            ),
        },
        expected_assertions=[
            _assert(
                "minimum_hours_priority_observed",
                "The full-time employee who needs hours should outrank the per-diem employee.",
                employee_id="CNA-FT-NEEDS-HOURS",
            ),
        ],
    ),
    ScenarioSpec(
        id="schedule-ideal-month-summary",
        title="Ideal monthly generation produces full coverage with no hidden warnings",
        business_rule=(
            "With enough staff for the simplified monthly model, the generated month "
            "should be fully covered, ideal, and free of hidden warning noise."
        ),
        result_classification="pass",
        setup=ScenarioSetup(
            units=[_unit("U-LT1", "Long-Term Unit 1", UnitTypology.LT)],
            staff=[
                *[
                    _staff(
                        f"RN-FULL{i}",
                        f"Coverage RN {i}",
                        LicenseType.RN,
                        "FT",
                        "U-LT1",
                        date(2019, 2, i),
                    )
                    for i in range(1, 6)
                ],
                *[
                    _staff(
                        f"CNA-FULL{i}",
                        f"Coverage CNA {i}",
                        LicenseType.CNA,
                        "FT",
                        "U-LT1",
                        date(2019, 3, i),
                    )
                    for i in range(1, 19)
                ],
            ],
        ),
        action={
            "kind": "generate_schedule",
            "request": GenerateScheduleRequest(year=2026, month=4),
        },
        expected_assertions=[
            _assert(
                "scenario_label_is",
                "The summary badge should report ideal coverage.",
                value="ideal",
            ),
            _assert(
                "unfilled_slots_at_most",
                "Ideal coverage should have no unfilled slots.",
                max_unfilled=0,
            ),
            _assert(
                "warning_count_at_most",
                "Ideal coverage should not generate warning rows.",
                max_warnings=0,
            ),
            _assert(
                "no_unassigned_slots",
                "The monthly schedule view should show every slot assigned.",
            ),
        ],
    ),
]
