"""Tests for the Kronos pay-period summary -> HoursLedger ingest adapter."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.integrations.timeclock.kronos_schema import KronosPayPeriodSummary
from app.integrations.timeclock.source import TimeClockSource
from app.models.base import Base
from app.models.hours import HoursLedger
from app.models.staff import (
    EmploymentClass as ModelEmploymentClass,
    LicenseType as ModelLicenseType,
    StaffMaster,
)
from app.services.timeclock_ingest import (
    ingest_pay_period_summaries,
    summary_to_ledger_record,
)


PERIOD_START = date(2026, 4, 6)
PERIOD_END = date(2026, 4, 19)


def _summary(
    person_number: str,
    *,
    regular: float = 64.0,
    overtime: float = 0.0,
    doubletime: float = 0.0,
    holiday: float = 0.0,
    sick: float = 0.0,
    pto: float = 0.0,
    shift_count: int = 8,
) -> KronosPayPeriodSummary:
    return KronosPayPeriodSummary(
        person_number=person_number,
        pay_period_start=PERIOD_START,
        pay_period_end=PERIOD_END,
        regular_hours=regular,
        overtime_hours=overtime,
        doubletime_hours=doubletime,
        holiday_hours=holiday,
        sick_hours=sick,
        pto_hours=pto,
        shift_count=shift_count,
    )


class FakeSource(TimeClockSource):
    """In-memory TimeClockSource that returns canned summaries by period."""

    def __init__(self, by_period: dict[date, list[KronosPayPeriodSummary]]):
        self._by_period = by_period

    async def fetch_punches(self, start_date, end_date):  # pragma: no cover
        raise NotImplementedError

    async def fetch_daily_totals(self, start_date, end_date):  # pragma: no cover
        raise NotImplementedError

    async def fetch_pay_period_summary(self, period_start):
        return list(self._by_period.get(period_start, []))


# --- Pure-function tests for the converter ---


class TestSummaryToLedgerRecord:
    def test_worked_excludes_pto_and_sick(self):
        s = _summary("CNA001", regular=40.0, overtime=8.0, sick=8.0, pto=8.0)
        rec = summary_to_ledger_record(s)
        # Worked = 40 + 8 (REG + OT). PTO/SICK do not count.
        assert rec.hours_this_cycle == pytest.approx(48.0)

    def test_includes_doubletime_and_holiday(self):
        s = _summary(
            "RN001", regular=40.0, overtime=4.0, doubletime=8.0, holiday=8.0
        )
        rec = summary_to_ledger_record(s)
        assert rec.hours_this_cycle == pytest.approx(60.0)

    def test_passes_through_shift_count_and_period(self):
        s = _summary("CNA001", shift_count=9)
        rec = summary_to_ledger_record(s)
        assert rec.employee_id == "CNA001"
        assert rec.cycle_start_date == PERIOD_START
        assert rec.shift_count_this_biweek == 9


# --- Integration test against an in-memory SQLite DB ---


@pytest.fixture
async def db_session():
    """Provide a fresh aiosqlite session for each test."""
    with tempfile.TemporaryDirectory(prefix="timeclock-ingest-") as tmp:
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(tmp) / 'test.db'}", future=True
        )
        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # HoursLedger rows reference staff_master via FK; seed minimal staff.
        async with session_factory() as s:
            s.add_all(
                [
                    StaffMaster(
                        employee_id=eid,
                        name=f"Test {eid}",
                        license=ModelLicenseType.CNA,
                        employment_class=ModelEmploymentClass.FT,
                        zip_code="11374",
                        is_active=True,
                    )
                    for eid in ("CNA001", "RN001", "CNA002")
                ]
            )
            await s.commit()

        async with session_factory() as session:
            yield session
        await engine.dispose()


async def test_ingest_creates_one_ledger_row_per_employee(db_session):
    source = FakeSource(
        {
            PERIOD_START: [
                _summary("CNA001", regular=64.0, overtime=4.0),
                _summary("RN001", regular=80.0, overtime=8.0),
            ]
        }
    )
    result = await ingest_pay_period_summaries(db_session, source, [PERIOD_START])
    assert result.created == 2
    assert result.updated == 0
    assert result.total == 2

    rows = (await db_session.execute(select(HoursLedger))).scalars().all()
    by_emp = {r.employee_id: r for r in rows}
    assert by_emp["CNA001"].hours_this_cycle == pytest.approx(68.0)
    assert by_emp["RN001"].hours_this_cycle == pytest.approx(88.0)


async def test_ingest_is_idempotent(db_session):
    """Re-running the same ingest must update, not duplicate, rows."""
    source = FakeSource(
        {PERIOD_START: [_summary("CNA001", regular=64.0)]}
    )
    await ingest_pay_period_summaries(db_session, source, [PERIOD_START])
    second = await ingest_pay_period_summaries(db_session, source, [PERIOD_START])
    assert second.created == 0
    assert second.updated == 1

    rows = (await db_session.execute(select(HoursLedger))).scalars().all()
    assert len(rows) == 1


async def test_ingest_handles_multiple_periods(db_session):
    later = date(2026, 4, 20)
    later_summary = KronosPayPeriodSummary(
        person_number="CNA002",
        pay_period_start=later,
        pay_period_end=date(2026, 5, 3),
        regular_hours=72.0,
        overtime_hours=0.0,
        doubletime_hours=0.0,
        holiday_hours=0.0,
        sick_hours=0.0,
        pto_hours=0.0,
        shift_count=9,
    )
    source = FakeSource(
        {
            PERIOD_START: [_summary("CNA001", regular=64.0)],
            later: [later_summary],
        }
    )
    result = await ingest_pay_period_summaries(
        db_session, source, [PERIOD_START, later]
    )
    assert result.created == 2

    rows = (await db_session.execute(select(HoursLedger))).scalars().all()
    starts = {r.cycle_start_date for r in rows}
    assert starts == {PERIOD_START, later}


async def test_ingest_with_empty_source_returns_zero_result(db_session):
    source = FakeSource({})
    result = await ingest_pay_period_summaries(db_session, source, [PERIOD_START])
    assert result.created == 0
    assert result.updated == 0
    assert result.total == 0
