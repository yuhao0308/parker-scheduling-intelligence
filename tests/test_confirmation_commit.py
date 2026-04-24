from __future__ import annotations

from datetime import date

import pytest

from app.config import Settings
from app.models.schedule import ConfirmationStatus
from app.schemas.common import ShiftLabel
from app.schemas.confirmation import CommitDecision, StatusCounts
from app.services import confirmation as confirmation_service


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _ScalarResult(self._rows)


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows
        self.flushed = False
        self.committed = False

    async def execute(self, _query):
        return _ExecuteResult(self._rows)

    async def flush(self):
        self.flushed = True

    async def commit(self):
        self.committed = True


class _Entry:
    def __init__(self):
        self.id = 101
        self.employee_id = "RN001"
        self.unit_id = "U-SA1"
        self.shift_date = date(2026, 4, 20)
        self.shift_label = ShiftLabel.DAY
        self.confirmation_status = ConfirmationStatus.PENDING
        self.confirmation_responded_at = None


@pytest.mark.asyncio
async def test_commit_decline_without_remaining_pool_returns_stop_warning(monkeypatch):
    async def fake_mark_latest_notification(*_args, **_kwargs):
        return None

    async def fake_status_counts(*_args, **_kwargs):
        return StatusCounts(declined=1)

    monkeypatch.setattr(
        confirmation_service, "_mark_latest_notification", fake_mark_latest_notification
    )
    monkeypatch.setattr(confirmation_service, "_status_counts", fake_status_counts)

    entry = _Entry()
    db = _FakeDb([entry])

    result = await confirmation_service.commit_week_decisions(
        db=db,
        week_start=date(2026, 4, 20),
        decisions=[CommitDecision(entry_id=entry.id, keep=False)],
        employee_pool=[entry.employee_id],
        settings=Settings(),
    )

    assert db.flushed is True
    assert db.committed is True
    assert entry.confirmation_status == ConfirmationStatus.DECLINED
    assert result.declined_count == 1
    assert result.unfilled_slots == 1
    assert result.candidate_exhausted is True
    assert result.stop_message is not None
    assert "No available candidates remain" in result.stop_message
    assert result.warnings == [
        "Unfilled after finalize: U-SA1 DAY 2026-04-20 [RN001 declined]"
    ]
