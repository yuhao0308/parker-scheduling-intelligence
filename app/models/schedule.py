from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.unit import ShiftLabel


class ConfirmationStatus(str, enum.Enum):
    UNSENT = "UNSENT"
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    REPLACED = "REPLACED"


class ScheduleEntry(TimestampMixin, Base):
    __tablename__ = "schedule_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(String(50), ForeignKey("staff_master.employee_id"))
    unit_id: Mapped[str] = mapped_column(String(50), ForeignKey("unit.unit_id"))
    shift_date: Mapped[date] = mapped_column(Date)
    shift_label: Mapped[ShiftLabel] = mapped_column(Enum(ShiftLabel))
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    is_clocked_in: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    confirmation_status: Mapped[ConfirmationStatus] = mapped_column(
        Enum(ConfirmationStatus, name="confirmation_status"),
        default=ConfirmationStatus.UNSENT,
        server_default=ConfirmationStatus.UNSENT.value,
        nullable=False,
    )
    confirmation_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmation_responded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replaced_by_entry_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("schedule_entry.id"), nullable=True
    )


class Callout(TimestampMixin, Base):
    __tablename__ = "callout"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(String(50), ForeignKey("staff_master.employee_id"))
    unit_id: Mapped[str] = mapped_column(String(50), ForeignKey("unit.unit_id"))
    shift_date: Mapped[date] = mapped_column(Date)
    shift_label: Mapped[ShiftLabel] = mapped_column(Enum(ShiftLabel))
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PTOEntry(Base):
    __tablename__ = "pto_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(String(50), ForeignKey("staff_master.employee_id"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
