from __future__ import annotations

import enum


class LicenseType(str, enum.Enum):
    RN = "RN"
    LPN = "LPN"
    CNA = "CNA"
    PCT = "PCT"


class EmploymentClass(str, enum.Enum):
    FT = "FT"
    PT = "PT"
    PER_DIEM = "PER_DIEM"


class ShiftLabel(str, enum.Enum):
    NIGHT = "NIGHT"
    DAY = "DAY"
    EVENING = "EVENING"


class UnitTypology(str, enum.Enum):
    LT = "LT"
    SUBACUTE = "SUBACUTE"


# Licensed roles can cover licensed requirements
LICENSED_ROLES = {LicenseType.RN, LicenseType.LPN}
# Certified roles can cover certified requirements
CERTIFIED_ROLES = {LicenseType.CNA, LicenseType.PCT}
