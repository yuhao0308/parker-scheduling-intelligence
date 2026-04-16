"""Shared test fixtures."""
from __future__ import annotations

from datetime import date

import pytest

from app.schemas.common import LicenseType, ShiftLabel
from app.services.filter import CandidateRecord


@pytest.fixture
def sample_candidates():
    """A pool of 6 diverse staff members for testing."""
    return [
        CandidateRecord(
            employee_id="RN001",
            name="Maria Rodriguez",
            license=LicenseType.RN,
            employment_class="FT",
            zip_code="11374",  # nearby, but not at the facility
            home_unit_id="U-SA1",
            home_unit_typology="SUBACUTE",
            cross_trained_unit_ids=["U-SA2"],
            hire_date=date(2019, 3, 15),
            is_active=True,
        ),
        CandidateRecord(
            employee_id="RN002",
            name="James Thompson",
            license=LicenseType.RN,
            employment_class="PT",
            zip_code="10301",  # Staten Island — farther
            home_unit_id="U-LT1",
            home_unit_typology="LT",
            cross_trained_unit_ids=[],
            hire_date=date(2023, 11, 1),
            is_active=True,
        ),
        CandidateRecord(
            employee_id="CNA001",
            name="Aisha Johnson",
            license=LicenseType.CNA,
            employment_class="FT",
            zip_code="11374",
            home_unit_id="U-SA1",
            home_unit_typology="SUBACUTE",
            cross_trained_unit_ids=["U-SA2", "U-LT1"],
            hire_date=date(2020, 6, 1),
            is_active=True,
        ),
        CandidateRecord(
            employee_id="CNA002",
            name="David Kim",
            license=LicenseType.CNA,
            employment_class="FT",
            zip_code="07030",  # NJ
            home_unit_id="U-LT2",
            home_unit_typology="LT",
            cross_trained_unit_ids=[],
            hire_date=date(2024, 1, 15),  # new hire
            is_active=True,
        ),
        CandidateRecord(
            employee_id="LPN001",
            name="Sarah Chen",
            license=LicenseType.LPN,
            employment_class="PER_DIEM",
            zip_code="11432",
            home_unit_id="U-LT3",
            home_unit_typology="LT",
            cross_trained_unit_ids=["U-LT1"],
            hire_date=date(2018, 9, 1),
            is_active=True,
        ),
        CandidateRecord(
            employee_id="CNA003",
            name="Mike Brown",
            license=LicenseType.CNA,
            employment_class="PER_DIEM",
            zip_code="11373",
            home_unit_id="U-SA2",
            home_unit_typology="SUBACUTE",
            cross_trained_unit_ids=["U-SA1"],
            hire_date=date(2021, 2, 1),
            is_active=True,
        ),
    ]
