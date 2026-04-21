from __future__ import annotations

import enum
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class OutreachResponse(str, enum.Enum):
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"


class SendOutreachRequest(BaseModel):
    recommendation_log_id: int
    candidate_employee_id: str
    rank: Optional[int] = None


class SendOutreachResult(BaseModel):
    notification_id: int
    callout_id: int
    employee_id: str
    rank: Optional[int] = None
    status: str


class RespondOutreachRequest(BaseModel):
    response: OutreachResponse
    rank: Optional[int] = None
    override_reason: Optional[str] = None


class OutreachNotificationOut(BaseModel):
    notification_id: int
    employee_id: str
    status: str
    created_at: datetime
    responded_at: Optional[datetime] = None
    rank: Optional[int] = None
    payload_text: Optional[str] = None


class RespondOutreachResult(BaseModel):
    notification_id: int
    status: str
    assigned_entry_id: Optional[int] = None
    canceled_notification_ids: List[int] = []
    deprioritized_employee_ids: List[str] = []
