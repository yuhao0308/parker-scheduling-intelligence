from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UnitExclusion(TimestampMixin, Base):
    __tablename__ = "unit_exclusion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(String(50), ForeignKey("staff_master.employee_id"))
    unit_id: Mapped[str] = mapped_column(String(50), ForeignKey("unit.unit_id"))
    reason: Mapped[str] = mapped_column(Text)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
