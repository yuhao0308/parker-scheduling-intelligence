from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class HoursLedger(Base):
    __tablename__ = "hours_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(String(50), ForeignKey("staff_master.employee_id"))
    cycle_start_date: Mapped[date] = mapped_column(Date)
    hours_this_cycle: Mapped[float] = mapped_column(Float, default=0.0)
    shift_count_this_biweek: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
