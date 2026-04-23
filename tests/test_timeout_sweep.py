"""Service-layer tests for timeout_sweep_entries.

Covers Rule 5 from tests/features/auto_gen_panel.feature — the single bulk
endpoint that transitions expired PENDING entries to DECLINED, replacing the
per-row TIMEOUT mutation pattern.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.notification import (
    NotificationChannel,
    NotificationKind,
    NotificationStatus,
    SimulatedNotification,
)
from app.models.schedule import Callout, ConfirmationStatus, ScheduleEntry
from app.models.staff import (
    EmploymentClass,
    LicenseType,
    StaffMaster,
)
from app.models.unit import ShiftLabel, Unit, UnitTypology
from app.services.confirmation import timeout_sweep_entries


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    # Import all models so metadata is fully populated before create_all.
    from app.models import hours, recommendation, exclusion  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def _seed_staff_and_unit(db: AsyncSession) -> None:
    db.add(
        Unit(
            unit_id="U-LT1",
            name="Long-Term 1",
            typology=UnitTypology.LT,
            required_ratio=0.5,
            is_active=True,
        )
    )
    db.add(
        StaffMaster(
            employee_id="E1",
            name="Employee One",
            license=LicenseType.CNA,
            employment_class=EmploymentClass.FT,
            zip_code="11374",
            is_active=True,
        )
    )
    db.add(
        StaffMaster(
            employee_id="E2",
            name="Employee Two",
            license=LicenseType.CNA,
            employment_class=EmploymentClass.FT,
            zip_code="11374",
            is_active=True,
        )
    )
    await db.flush()


def _make_entry(
    employee_id: str,
    shift_date: date,
    status: ConfirmationStatus,
    sent_minutes_ago: int | None = None,
) -> ScheduleEntry:
    sent_at = None
    if sent_minutes_ago is not None:
        sent_at = datetime.now(timezone.utc) - timedelta(minutes=sent_minutes_ago)
    return ScheduleEntry(
        employee_id=employee_id,
        unit_id="U-LT1",
        shift_date=shift_date,
        shift_label=ShiftLabel.DAY,
        is_published=True,
        confirmation_status=status,
        confirmation_sent_at=sent_at,
    )


# ---------------------------------------------------------------------------
# Rule 5 / Scenario: bulk sweep processes all expired PENDING entry_ids
# ---------------------------------------------------------------------------
async def test_sweep_transitions_pending_entries_to_declined(db: AsyncSession):
    await _seed_staff_and_unit(db)
    e1 = _make_entry("E1", date(2026, 4, 20), ConfirmationStatus.PENDING, sent_minutes_ago=30)
    e2 = _make_entry("E2", date(2026, 4, 21), ConfirmationStatus.PENDING, sent_minutes_ago=45)
    db.add_all([e1, e2])
    await db.flush()

    result = await timeout_sweep_entries(db, [e1.id, e2.id])

    assert sorted(result.processed) == sorted([e1.id, e2.id])
    assert result.skipped == []
    await db.refresh(e1)
    await db.refresh(e2)
    assert e1.confirmation_status == ConfirmationStatus.DECLINED
    assert e2.confirmation_status == ConfirmationStatus.DECLINED
    assert e1.confirmation_responded_at is not None


# ---------------------------------------------------------------------------
# Rule 5 / Scenario: non-PENDING entries are skipped, not raised
# ---------------------------------------------------------------------------
async def test_sweep_skips_non_pending_entries_without_raising(db: AsyncSession):
    """Races with manual Accept/Decline are expected. Sweep must not throw
    when an entry_id is already ACCEPTED/DECLINED — it just reports it in
    skipped."""
    await _seed_staff_and_unit(db)
    accepted = _make_entry(
        "E1", date(2026, 4, 20), ConfirmationStatus.ACCEPTED, sent_minutes_ago=30
    )
    declined = _make_entry(
        "E2", date(2026, 4, 21), ConfirmationStatus.DECLINED, sent_minutes_ago=45
    )
    pending = _make_entry(
        "E1", date(2026, 4, 22), ConfirmationStatus.PENDING, sent_minutes_ago=30
    )
    db.add_all([accepted, declined, pending])
    await db.flush()

    result = await timeout_sweep_entries(
        db, [accepted.id, declined.id, pending.id, 999999]
    )

    assert result.processed == [pending.id]
    assert sorted(result.skipped) == sorted([accepted.id, declined.id, 999999])
    await db.refresh(accepted)
    await db.refresh(declined)
    assert accepted.confirmation_status == ConfirmationStatus.ACCEPTED
    assert declined.confirmation_status == ConfirmationStatus.DECLINED


# ---------------------------------------------------------------------------
# Rule 5 / Scenario: sweep creates a Callout record per processed entry
# ---------------------------------------------------------------------------
async def test_sweep_records_a_callout_per_processed_entry(db: AsyncSession):
    await _seed_staff_and_unit(db)
    e1 = _make_entry("E1", date(2026, 4, 20), ConfirmationStatus.PENDING, sent_minutes_ago=30)
    db.add(e1)
    await db.flush()

    await timeout_sweep_entries(db, [e1.id])

    from sqlalchemy import select

    callouts = (await db.execute(select(Callout))).scalars().all()
    assert len(callouts) == 1
    assert callouts[0].employee_id == "E1"
    assert callouts[0].reason == "schedule_decline:timeout"


# ---------------------------------------------------------------------------
# Rule 5 / Scenario: sweep flips the latest CONFIRM_SHIFT notification to TIMEOUT
# ---------------------------------------------------------------------------
async def test_sweep_marks_latest_notification_as_timeout(db: AsyncSession):
    await _seed_staff_and_unit(db)
    e1 = _make_entry("E1", date(2026, 4, 20), ConfirmationStatus.PENDING, sent_minutes_ago=30)
    db.add(e1)
    await db.flush()
    notif = SimulatedNotification(
        schedule_entry_id=e1.id,
        employee_id="E1",
        channel=NotificationChannel.SMS,
        kind=NotificationKind.CONFIRM_SHIFT,
        status=NotificationStatus.SENT,
        payload_text="please confirm",
        created_at=datetime.now(timezone.utc),
    )
    db.add(notif)
    await db.flush()

    await timeout_sweep_entries(db, [e1.id])
    await db.refresh(notif)

    assert notif.status == NotificationStatus.TIMEOUT
    assert notif.responded_at is not None


# ---------------------------------------------------------------------------
# Rule 5 / Scenario: sweep is idempotent — running it twice on the same ids
# leaves things stable (second call skips everything).
# ---------------------------------------------------------------------------
async def test_sweep_is_idempotent_on_already_processed_ids(db: AsyncSession):
    await _seed_staff_and_unit(db)
    e1 = _make_entry("E1", date(2026, 4, 20), ConfirmationStatus.PENDING, sent_minutes_ago=30)
    db.add(e1)
    await db.flush()

    first = await timeout_sweep_entries(db, [e1.id])
    second = await timeout_sweep_entries(db, [e1.id])

    assert first.processed == [e1.id]
    assert second.processed == []
    assert second.skipped == [e1.id]


# ---------------------------------------------------------------------------
# Rule 5 / Scenario: empty entry_ids list is a no-op (no crash, empty result)
# ---------------------------------------------------------------------------
async def test_sweep_with_empty_list_is_noop(db: AsyncSession):
    await _seed_staff_and_unit(db)
    result = await timeout_sweep_entries(db, [])
    assert result.processed == []
    assert result.skipped == []
