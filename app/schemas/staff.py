from __future__ import annotations

from datetime import date
from typing import List

from pydantic import BaseModel

from app.schemas.common import EmploymentClass, LicenseType


class StaffSyncRecord(BaseModel):
    employee_id: str
    name: str
    license: LicenseType
    employment_class: EmploymentClass
    zip_code: str
    home_unit_id: str
    cross_trained_units: List[str] = []
    hire_date: date
    is_active: bool = True


class StaffSyncPayload(BaseModel):
    records: List[StaffSyncRecord]


class SyncResult(BaseModel):
    created: int
    updated: int
    total: int
