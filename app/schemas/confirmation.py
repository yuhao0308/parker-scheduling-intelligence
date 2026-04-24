from __future__ import annotations

import enum
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.callout import CalloutResponse


class ConfirmationResponse(str, enum.Enum):
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    TIMEOUT = "TIMEOUT"


class SendConfirmationsRequest(BaseModel):
    week_start: date
    unit_ids: Optional[List[str]] = None


class SendMonthlyConfirmationsRequest(BaseModel):
    year: int
    month: int
    unit_ids: Optional[List[str]] = None


class StatusCounts(BaseModel):
    unsent: int = 0
    pending: int = 0
    accepted: int = 0
    declined: int = 0
    replaced: int = 0


class SendConfirmationsResult(BaseModel):
    week_start: date
    entries_marked: int
    notifications_created: int
    counts_by_status: StatusCounts


class ConfirmationEntryOut(BaseModel):
    entry_id: int
    employee_id: str
    name: str
    license: str
    unit_id: str
    unit_name: str
    shift_date: date
    shift_label: str
    confirmation_status: str
    confirmation_sent_at: Optional[datetime] = None
    confirmation_responded_at: Optional[datetime] = None
    latest_notification_id: Optional[int] = None


class ConfirmationListOut(BaseModel):
    week_start: date
    entries: List[ConfirmationEntryOut]
    summary: StatusCounts


class RespondConfirmationRequest(BaseModel):
    response: ConfirmationResponse


class RespondConfirmationResult(BaseModel):
    entry_id: int
    new_status: str
    replacement: Optional[CalloutResponse] = None


class CommitDecision(BaseModel):
    entry_id: int
    keep: bool = True


class CommitDecisionsRequest(BaseModel):
    week_start: date
    employee_pool: List[str]
    decisions: List[CommitDecision]


class CommitMonthlyDecisionsRequest(BaseModel):
    year: int
    month: int
    employee_pool: List[str]
    decisions: List[CommitDecision]


class CommitDecisionsResult(BaseModel):
    week_start: date
    accepted_count: int
    declined_count: int
    skipped_count: int
    declined_employee_ids: List[str]
    reroll_entries_generated: int = 0
    reroll_notifications_sent: int = 0
    unfilled_slots: int = 0
    warnings: List[str] = []
    summary: StatusCounts


class ReplaceEntryRequest(BaseModel):
    recommendation_log_id: int
    selected_employee_id: str
    selected_rank: Optional[int] = None


class ReplaceEntryResult(BaseModel):
    old_entry_id: int
    new_entry_id: int
    new_status: str


class RemoveEntryResult(BaseModel):
    entry_id: int
    new_status: str
    slot_now_open: bool = True
    canceled_notification_id: Optional[int] = None


class TimeoutSweepRequest(BaseModel):
    entry_ids: List[int]


class TimeoutSweepResult(BaseModel):
    processed: List[int]
    skipped: List[int]
    processed_at: datetime
