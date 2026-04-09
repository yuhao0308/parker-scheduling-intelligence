from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.unit import ShiftLabel


class RecommendationLog(Base):
    __tablename__ = "recommendation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    callout_id: Mapped[int] = mapped_column(Integer, ForeignKey("callout.id"))
    request_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    target_unit_id: Mapped[str] = mapped_column(String(50), ForeignKey("unit.unit_id"))
    target_shift_label: Mapped[ShiftLabel] = mapped_column(Enum(ShiftLabel))
    target_shift_date: Mapped[date] = mapped_column(Date)
    ranked_candidates: Mapped[dict] = mapped_column(JSONB)
    filter_stats: Mapped[dict] = mapped_column(JSONB)


class OverrideLog(Base):
    __tablename__ = "override_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_log_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recommendation_log.id")
    )
    selected_employee_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("staff_master.employee_id")
    )
    selected_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    coordinator_id: Mapped[str] = mapped_column(String(100))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
