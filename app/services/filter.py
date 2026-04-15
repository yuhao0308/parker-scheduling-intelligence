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
    # (unit_id, shift_date, shift_label) -> license bucket counts for staff
    # currently rostered on that unit/shift. Used for coverage-floor filtering.
    unit_shift_license_counts: dict[tuple[str, date, ShiftLabel], dict[LicenseType, int]] = field(
        default_factory=dict
    )


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


def filter_source_unit_coverage(
    candidates: list[CandidateRecord],
    schedule: ScheduleContext,
    target_unit_id: str,
    target_date: date,
    target_label: ShiftLabel,
    unit_min_licensed: dict[str, int],
    unit_min_certified: dict[str, int],
) -> tuple[list[CandidateRecord], int]:
    """Protect source unit minimums when pulling a floater.

    If a candidate is currently rostered on their home unit for the same
    shift as the open call-out, pulling them would drop their home unit
    below the regulatory minimum. These candidates are eliminated.

    Staff who are NOT currently scheduled on the target shift (the typical
    pickup case) pass through — they are not being removed from anywhere.
    """
    passed: list[CandidateRecord] = []
    filtered = 0
    for c in candidates:
        if c.home_unit_id == target_unit_id:
            passed.append(c)
            continue

        # Is this candidate rostered on their home unit for the callout shift?
        rostered_on_home = False
        for sd, sl in schedule.employee_shifts.get(c.employee_id, []):
            if sd == target_date and sl == target_label:
                rostered_on_home = True
                break
        if not rostered_on_home:
            passed.append(c)
            continue

        counts = schedule.unit_shift_license_counts.get(
            (c.home_unit_id, target_date, target_label), {}
        )
        licensed_count = sum(counts.get(l, 0) for l in LICENSED_ROLES)
        certified_count = sum(counts.get(l, 0) for l in CERTIFIED_ROLES)

        min_lic = unit_min_licensed.get(c.home_unit_id, 1)
        min_cert = unit_min_certified.get(c.home_unit_id, 0)

        if c.license in LICENSED_ROLES and (licensed_count - 1) < min_lic:
            filtered += 1
            continue
        if c.license in CERTIFIED_ROLES and (certified_count - 1) < min_cert:
            filtered += 1
            continue
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
    unit_min_licensed: dict[str, int] | None = None,
    unit_min_certified: dict[str, int] | None = None,
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

    if unit_min_licensed is not None and unit_min_certified is not None:
        pool, n = filter_source_unit_coverage(
            pool,
            schedule,
            target_unit_id,
            target_date,
            target_label,
            unit_min_licensed,
            unit_min_certified,
        )
        if n:
            stats["source_unit_coverage_floor"] = n

    return FilterResult(passed=pool, stats=stats, total_pool=total)
