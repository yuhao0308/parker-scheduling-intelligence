"""Tests for the hard-filter pipeline."""
from __future__ import annotations

from datetime import date

import pytest

from app.schemas.common import LicenseType, ShiftLabel
from app.services.filter import (
    ExclusionRecord,
    ScheduleContext,
    apply_hard_filters,
    filter_already_scheduled,
    filter_exclusions,
    filter_license_mismatch,
    filter_rest_window,
)


class TestLicenseFilter:
    def test_filters_cna_for_rn_requirement(self, sample_candidates):
        passed, filtered = filter_license_mismatch(sample_candidates, LicenseType.RN)
        # Only RN001, RN002, LPN001 should pass (licensed roles)
        passed_ids = {c.employee_id for c in passed}
        assert passed_ids == {"RN001", "RN002", "LPN001"}
        assert filtered == 3

    def test_filters_rn_for_cna_requirement(self, sample_candidates):
        passed, filtered = filter_license_mismatch(sample_candidates, LicenseType.CNA)
        passed_ids = {c.employee_id for c in passed}
        assert passed_ids == {"CNA001", "CNA002", "CNA003"}
        assert filtered == 3

    def test_pct_passes_for_cna_requirement(self, sample_candidates):
        """PCT is in the certified bucket, should pass for CNA requirement."""
        from app.services.filter import CandidateRecord
        pct = CandidateRecord(
            employee_id="PCT001", name="Test PCT", license=LicenseType.PCT,
            employment_class="FT", zip_code="11375", home_unit_id="U-LT1",
            home_unit_typology="LT", cross_trained_unit_ids=[], hire_date=date(2020, 1, 1),
            is_active=True,
        )
        passed, filtered = filter_license_mismatch([pct], LicenseType.CNA)
        assert len(passed) == 1


class TestScheduleFilter:
    def test_filters_scheduled_employee(self, sample_candidates):
        ctx = ScheduleContext(
            employee_shifts={},
            employees_on_pto=set(),
            employees_scheduled={"CNA001"},
        )
        passed, filtered = filter_already_scheduled(sample_candidates, ctx)
        assert filtered == 1
        assert "CNA001" not in {c.employee_id for c in passed}

    def test_filters_pto_employee(self, sample_candidates):
        ctx = ScheduleContext(
            employee_shifts={},
            employees_on_pto={"RN001"},
            employees_scheduled=set(),
        )
        passed, filtered = filter_already_scheduled(sample_candidates, ctx)
        assert filtered == 1
        assert "RN001" not in {c.employee_id for c in passed}

    def test_no_filter_when_nobody_scheduled(self, sample_candidates):
        ctx = ScheduleContext(
            employee_shifts={}, employees_on_pto=set(), employees_scheduled=set()
        )
        passed, filtered = filter_already_scheduled(sample_candidates, ctx)
        assert filtered == 0
        assert len(passed) == len(sample_candidates)


class TestExclusionFilter:
    def test_active_exclusion_filters(self, sample_candidates):
        exclusions = [
            ExclusionRecord(
                employee_id="CNA001", unit_id="U-SA1",
                effective_from=date(2026, 4, 1), effective_until=date(2026, 4, 30),
            )
        ]
        passed, filtered = filter_exclusions(
            sample_candidates, exclusions, "U-SA1", date(2026, 4, 9)
        )
        assert filtered == 1
        assert "CNA001" not in {c.employee_id for c in passed}

    def test_expired_exclusion_does_not_filter(self, sample_candidates):
        exclusions = [
            ExclusionRecord(
                employee_id="CNA001", unit_id="U-SA1",
                effective_from=date(2026, 3, 1), effective_until=date(2026, 3, 31),
            )
        ]
        passed, filtered = filter_exclusions(
            sample_candidates, exclusions, "U-SA1", date(2026, 4, 9)
        )
        assert filtered == 0

    def test_indefinite_exclusion_filters(self, sample_candidates):
        exclusions = [
            ExclusionRecord(
                employee_id="RN002", unit_id="U-SA1",
                effective_from=date(2026, 1, 1), effective_until=None,
            )
        ]
        passed, filtered = filter_exclusions(
            sample_candidates, exclusions, "U-SA1", date(2026, 4, 9)
        )
        assert filtered == 1
        assert "RN002" not in {c.employee_id for c in passed}

    def test_exclusion_for_different_unit_does_not_filter(self, sample_candidates):
        exclusions = [
            ExclusionRecord(
                employee_id="CNA001", unit_id="U-LT5",
                effective_from=date(2026, 4, 1), effective_until=date(2026, 4, 30),
            )
        ]
        passed, filtered = filter_exclusions(
            sample_candidates, exclusions, "U-SA1", date(2026, 4, 9)
        )
        assert filtered == 0

    def test_future_exclusion_does_not_filter(self, sample_candidates):
        exclusions = [
            ExclusionRecord(
                employee_id="CNA001", unit_id="U-SA1",
                effective_from=date(2026, 5, 1), effective_until=date(2026, 5, 31),
            )
        ]
        passed, filtered = filter_exclusions(
            sample_candidates, exclusions, "U-SA1", date(2026, 4, 9)
        )
        assert filtered == 0


class TestRestWindowFilter:
    def test_no_shifts_passes(self, sample_candidates):
        ctx = ScheduleContext(
            employee_shifts={}, employees_on_pto=set(), employees_scheduled=set()
        )
        passed, filtered = filter_rest_window(
            sample_candidates, ctx, date(2026, 4, 9), ShiftLabel.DAY
        )
        assert filtered == 0

    def test_two_shifts_blocks(self, sample_candidates):
        ctx = ScheduleContext(
            employee_shifts={
                "CNA001": [
                    (date(2026, 4, 8), ShiftLabel.NIGHT),  # op day Apr 9
                    (date(2026, 4, 9), ShiftLabel.DAY),     # op day Apr 9
                ]
            },
            employees_on_pto=set(),
            employees_scheduled=set(),
        )
        passed, filtered = filter_rest_window(
            sample_candidates, ctx, date(2026, 4, 9), ShiftLabel.EVENING
        )
        assert filtered == 1
        assert "CNA001" not in {c.employee_id for c in passed}


class TestApplyHardFilters:
    def test_full_pipeline(self, sample_candidates):
        ctx = ScheduleContext(
            employee_shifts={},
            employees_on_pto={"CNA002"},
            employees_scheduled=set(),
        )
        result = apply_hard_filters(
            candidates=sample_candidates,
            required_license=LicenseType.CNA,
            schedule=ctx,
            exclusions=[],
            target_unit_id="U-SA1",
            target_date=date(2026, 4, 9),
            target_label=ShiftLabel.DAY,
        )
        # 6 total, 3 filtered by license (RN001, RN002, LPN001),
        # 1 filtered by PTO (CNA002)
        assert result.total_pool == 6
        assert len(result.passed) == 2  # CNA001, CNA003
        assert result.stats.get("license_mismatch") == 3
        assert result.stats.get("already_scheduled_or_pto") == 1
