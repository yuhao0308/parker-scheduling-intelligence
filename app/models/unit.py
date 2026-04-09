from __future__ import annotations

import enum
from datetime import time

from sqlalchemy import Enum, Float, Integer, String, Time, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class UnitTypology(str, enum.Enum):
    LT = "LT"
    SUBACUTE = "SUBACUTE"


class ShiftLabel(str, enum.Enum):
    NIGHT = "NIGHT"      # 23:00 - 07:15
    DAY = "DAY"          # 07:00 - 15:15
    EVENING = "EVENING"  # 15:00 - 23:15


class Unit(TimestampMixin, Base):
    __tablename__ = "unit"

    unit_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    typology: Mapped[UnitTypology] = mapped_column(Enum(UnitTypology))
    required_ratio: Mapped[float] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ShiftWindow(Base):
    __tablename__ = "shift_window"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unit_id: Mapped[str] = mapped_column(String(50), ForeignKey("unit.unit_id"))
    shift_label: Mapped[ShiftLabel] = mapped_column(Enum(ShiftLabel))
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
