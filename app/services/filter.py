"""Hard-filter pipeline for candidate elimination.

These filters are NOT penalties — they are binary eliminators.
If a candidate fails any filter, they are removed from the pool entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.schemas.common import CERTIFIED_ROLES, LICENSED_ROLES, LicenseType, ShiftLabel
from app.services.shift_utils import count_shifts_in_operational_day


@dataclass
class CandidateRecord:
    """Lightweight view of a staff member for filtering/scoring."""

    employee_id: str
    name: str
    license: LicenseType
    employment_class: str
    zip_code: str
    home_unit_id: str
    home_unit_typology: str
    cross_trained_unit_ids: list[str]
    hire_date: date
    is_active: bool


@dataclass
class ScheduleContext:
    """Schedule state needed for filtering."""

    # employee_id -> list of (shift_date, shift_label) for recent shifts
    employee_shifts: dict[str, list[tuple[date, ShiftLabel]]]
    # employee_ids on PTO for the target date
    employees_on_pto: set[str]
    # employee_ids already scheduled for the target shift
    employees_scheduled: set[str]


@dataclass
class FilterResult:
    """Result of the filter pipeline."""

    passed: list[CandidateRecord]
    stats: dict[str, int] = field(default_factory=dict)
    total_pool: int = 0


def filter_license_mismatch(
    candidates: list[CandidateRecord],
    required_license: LicenseType,
) -> tuple[list[CandidateRecord], int]:
    """Remove candidates whose license doesn't match the requirement.

    Licensed requirement (RN/LPN) -> only RN or LPN can fill
    Certified requirement (CNA/PCT) -> only CNA or PCT can fill
    """
    if required_license in LICENSED_ROLES:
        allowed = LICENSED_ROLES
    else:
        allowed = CERTIFIED_ROLES

    passed = [c for c in candidates if c.license in allowed]
    return passed, len(candidates) - len(passed)


def filter_already_scheduled(
    candidates: list[CandidateRecord],
    schedule: ScheduleContext,
) -> tuple[list[CandidateRecord], int]:
    """Remove candidates already scheduled for the target shift or on PTO."""
    unavailable = schedule.employees_scheduled | schedule.employees_on_pto
    passed = [c for c in candidates if c.employee_id not in unavailable]
    return passed, len(candidates) - len(passed)


@dataclass
class ExclusionRecord:
    employee_id: str
    unit_id: str
    effective_from: date
    effective_until: date | None  # None = indefinite


def filter_exclusions(
    candidates: list[CandidateRecord],
    exclusions: list[ExclusionRecord],
    target_unit_id: str,
    target_date: date,
) -> tuple[list[CandidateRecord], int]:
    """Remove candidates with active exclusions for the target unit."""
    excluded_employees: set[str] = set()
    for exc in exclusions:
        if exc.unit_id != target_unit_id:
            continue
        if exc.effective_from > target_date:
            continue
        if exc.effective_until is not None and exc.effective_until < target_date:
            continue
        excluded_employees.add(exc.employee_id)

    passed = [c for c in candidates if c.employee_id not in excluded_employees]
    return passed, len(candidates) - len(passed)


def filter_rest_window(
    candidates: list[CandidateRecord],
    schedule: ScheduleContext,
    target_date: date,
    target_label: ShiftLabel,
    max_shifts_per_day: int = 2,
) -> tuple[list[CandidateRecord], int]:
    """Remove candidates who would exceed max shifts in the 24h operational window."""
    passed = []
    filtered = 0
    for c in candidates:
        shifts = schedule.employee_shifts.get(c.employee_id, [])
        existing_count = count_shifts_in_operational_day(shifts, target_date, target_label)
        if existing_count >= max_shifts_per_day:
            filtered += 1
        else:
            passed.append(c)
    return passed, filtered


def apply_hard_filters(
    candidates: list[CandidateRecord],
    required_license: LicenseType,
    schedule: ScheduleContext,
    exclusions: list[ExclusionRecord],
    target_unit_id: str,
    target_date: date,
    target_label: ShiftLabel,
) -> FilterResult:
    """Run all hard filters in sequence. Returns surviving candidates + stats."""
    total = len(candidates)
    stats: dict[str, int] = {}
    pool = candidates

    pool, n = filter_license_mismatch(pool, required_license)
    if n:
        stats["license_mismatch"] = n

    pool, n = filter_already_scheduled(pool, schedule)
    if n:
        stats["already_scheduled_or_pto"] = n

    pool, n = filter_exclusions(pool, exclusions, target_unit_id, target_date)
    if n:
        stats["exclusion"] = n

    pool, n = filter_rest_window(pool, schedule, target_date, target_label)
    if n:
        stats["rest_window_violation"] = n

    return FilterResult(passed=pool, stats=stats, total_pool=total)
