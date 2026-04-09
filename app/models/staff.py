from __future__ import annotations

import enum
from datetime import date
from typing import Optional

from sqlalchemy import Boolean, Date, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class LicenseType(str, enum.Enum):
    RN = "RN"
    LPN = "LPN"
    CNA = "CNA"
    PCT = "PCT"


class EmploymentClass(str, enum.Enum):
    FT = "FT"
    PT = "PT"
    PER_DIEM = "PER_DIEM"


class StaffMaster(TimestampMixin, Base):
    __tablename__ = "staff_master"

    employee_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    license: Mapped[LicenseType] = mapped_column(Enum(LicenseType))
    employment_class: Mapped[EmploymentClass] = mapped_column(Enum(EmploymentClass))
    zip_code: Mapped[str] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    ops: Mapped[Optional[StaffOps]] = relationship(back_populates="staff", uselist=False)
    cross_trainings: Mapped[list[StaffCrossTraining]] = relationship(back_populates="staff")


class StaffOps(TimestampMixin, Base):
    __tablename__ = "staff_ops"

    employee_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("staff_master.employee_id"), primary_key=True
    )
    home_unit_id: Mapped[str] = mapped_column(String(50), ForeignKey("unit.unit_id"))
    hire_date: Mapped[date] = mapped_column(Date)

    staff: Mapped[StaffMaster] = relationship(back_populates="ops")


class StaffCrossTraining(Base):
    __tablename__ = "staff_cross_training"

    employee_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("staff_master.employee_id"), primary_key=True
    )
    unit_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("unit.unit_id"), primary_key=True
    )

    staff: Mapped[StaffMaster] = relationship(back_populates="cross_trainings")
