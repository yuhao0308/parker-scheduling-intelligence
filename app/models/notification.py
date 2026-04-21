from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationChannel(str, enum.Enum):
    SMS = "SMS"
    EMAIL = "EMAIL"


class NotificationKind(str, enum.Enum):
    CONFIRM_SHIFT = "CONFIRM_SHIFT"
    CALLOUT_OUTREACH = "CALLOUT_OUTREACH"


class NotificationStatus(str, enum.Enum):
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"
    CANCELED = "CANCELED"


class SimulatedNotification(Base):
    __tablename__ = "simulated_notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_entry_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("schedule_entry.id"), nullable=True
    )
    callout_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("callout.id"), nullable=True
    )
    recommendation_log_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("recommendation_log.id"), nullable=True
    )
    employee_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("staff_master.employee_id")
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel"),
        default=NotificationChannel.SMS,
        nullable=False,
    )
    kind: Mapped[NotificationKind] = mapped_column(
        Enum(NotificationKind, name="notification_kind"), nullable=False
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus, name="notification_status"),
        default=NotificationStatus.SENT,
        nullable=False,
    )
    payload_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
