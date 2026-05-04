from __future__ import annotations

import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.integrations.timeclock.kronos_schema import KronosDailyTotal, PayCode
from app.models.base import Base
from app.models.hours import HoursLedger
from app.models.schedule import ScheduleEntry
from app.models.staff import (
    EmploymentClass as ModelEmploymentClass,
    LicenseType as ModelLicenseType,
    StaffMaster,
    StaffOps,
)
from app.models.unit import ShiftLabel as ModelShiftLabel
from app.models.unit import Unit, UnitTypology as ModelUnitTypology
from app.schemas.common import EmploymentClass
from app.services.overtime import cycle_budget_hours
from app.services.workload import (
    _worked_hours_by_employee_from_daily_totals,
    _view_cycle_start,
    build_work_hours_snapshot,
    summarize_rn_schedule,
    summarize_standard_schedule,
)


def test_standard_schedule_summarizes_peak_week_and_ot_hours():
    shifts = [
        date(2026, 4, 6),
        date(2026, 4, 7),
        date(2026, 4, 8),
        date(2026, 4, 9),
        date(2026, 4, 10),
    ]

    peak_week_hours, overtime_hours = summarize_standard_schedule(shifts)

    assert peak_week_hours == pytest.approx(41.25)
    assert overtime_hours == pytest.approx(3.75)


def test_rn_schedule_tracks_biweekly_shift_pressure():
    shifts = [
        (date(2026, 4, 6), "DAY"),
        (date(2026, 4, 7), "DAY"),
        (date(2026, 4, 8), "DAY"),
        (date(2026, 4, 9), "DAY"),
        (date(2026, 4, 10), "DAY"),
        (date(2026, 4, 11), "DAY"),
        (date(2026, 4, 12), "DAY"),
        (date(2026, 4, 13), "DAY"),
        (date(2026, 4, 14), "DAY"),
        (date(2026, 4, 15), "DAY"),
        (date(2026, 4, 16), "DAY"),
    ]

    double_shift_days, peak_biweekly_shifts, overtime_shifts = summarize_rn_schedule(
        shifts,
        cycle_anchor=date(2026, 4, 6),
    )

    assert double_shift_days == 0
    assert peak_biweekly_shifts == 11
    assert overtime_shifts == 1


def test_rn_schedule_detects_double_shift_days():
    shifts = [
        (date(2026, 4, 9), "DAY"),
        (date(2026, 4, 9), "EVENING"),
        (date(2026, 4, 10), "DAY"),
    ]

    double_shift_days, peak_biweekly_shifts, overtime_shifts = summarize_rn_schedule(
        shifts,
        cycle_anchor=date(2026, 4, 6),
    )

    assert double_shift_days == 1
    assert peak_biweekly_shifts == 3
    assert overtime_shifts == 0


class TestCycleBudgetHours:
    """Workload-monitor budget defaults — drives the white "remaining" segment."""

    def test_full_time_is_eighty_hours(self):
        assert cycle_budget_hours(EmploymentClass.FT) == 80.0

    def test_part_time_is_sixty_hours(self):
        assert cycle_budget_hours(EmploymentClass.PT) == 60.0

    def test_per_diem_is_forty_hours(self):
        assert cycle_budget_hours(EmploymentClass.PER_DIEM) == 40.0


class TestViewCycleStart:
    """Cycle anchor selection per view month — drives the workload bar.

    Cycles are aligned to the seed's known Monday anchor (2026-03-30) and
    must always land on a 14-day boundary regardless of how far the view
    is from the anchor.
    """

    def test_april_view_returns_march_30_anchor(self):
        # April 1 falls in the same cycle as the anchor.
        assert _view_cycle_start(2026, 4) == date(2026, 3, 30)

    def test_may_view_returns_april_27_cycle(self):
        # May 1 falls in the cycle starting Apr 27 — this is the bug fix:
        # without it, the bar kept showing the latest-historical cycle and
        # missed the schedule the user just arranged for May.
        assert _view_cycle_start(2026, 5) == date(2026, 4, 27)

    def test_february_view_returns_january_cycle(self):
        # Feb 1 falls in the cycle starting Jan 19 — proves we walk
        # backwards correctly across the anchor.
        assert _view_cycle_start(2026, 2) == date(2026, 1, 19)

    def test_march_view_returns_march_2_cycle(self):
        # Mar 1 is in the Mar 2 cycle's predecessor (Feb 16 -> Mar 1).
        assert _view_cycle_start(2026, 3) == date(2026, 2, 16)

    def test_result_is_always_on_a_14_day_boundary(self):
        anchor = date(2026, 3, 30)
        for month in range(1, 13):
            cycle = _view_cycle_start(2026, month)
            assert (cycle - anchor).days % 14 == 0


class TestMonthlyActuals:
    def test_daily_totals_count_productive_hours_but_not_pto(self):
        totals = [
            KronosDailyTotal(
                person_number="CNA001",
                work_date=date(2026, 4, 29),
                pay_code=PayCode.REG,
                hours=8.0,
                job="UNITED_HEBREW/U-SA1/CNA",
                labor_level_1="UNITED_HEBREW",
                labor_level_2="U-SA1",
                labor_level_3="CNA",
                shift_count=1,
            ),
            KronosDailyTotal(
                person_number="CNA001",
                work_date=date(2026, 4, 29),
                pay_code=PayCode.OT,
                hours=1.25,
                job="UNITED_HEBREW/U-SA1/CNA",
                labor_level_1="UNITED_HEBREW",
                labor_level_2="U-SA1",
                labor_level_3="CNA",
                shift_count=0,
            ),
            KronosDailyTotal(
                person_number="CNA001",
                work_date=date(2026, 4, 30),
                pay_code=PayCode.PTO,
                hours=8.0,
                job="UNITED_HEBREW/U-SA1/CNA",
                labor_level_1="UNITED_HEBREW",
                labor_level_2="U-SA1",
                labor_level_3="CNA",
                shift_count=0,
            ),
        ]

        actuals = _worked_hours_by_employee_from_daily_totals(totals)

        assert actuals["CNA001"] == pytest.approx((9.25, 1))


class FakeTimeClockSource:
    def __init__(self, totals: list[KronosDailyTotal] | None = None) -> None:
        self.totals = totals or []

    async def fetch_punches(self, start_date, end_date):  # pragma: no cover
        return []

    async def fetch_daily_totals(self, start_date, end_date):
        return [
            total
            for total in self.totals
            if start_date <= total.work_date <= end_date
        ]

    async def fetch_pay_period_summary(self, period_start):  # pragma: no cover
        return []


@pytest.fixture
async def workload_db():
    with tempfile.TemporaryDirectory(prefix="workload-") as tmp:
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(tmp) / 'test.db'}",
            future=True,
        )
        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            yield session
        await engine.dispose()


async def test_future_month_keeps_ot_cycle_actuals_but_month_actuals_are_zero(
    workload_db,
):
    workload_db.add(
        Unit(
            unit_id="U-SA1",
            name="Subacute 1",
            typology=ModelUnitTypology.SUBACUTE,
            required_ratio=1.0,
            is_active=True,
        )
    )
    workload_db.add(
        StaffMaster(
            employee_id="CNA001",
            name="Aisha Johnson",
            license=ModelLicenseType.CNA,
            employment_class=ModelEmploymentClass.FT,
            zip_code="11374",
            is_active=True,
        )
    )
    workload_db.add(
        StaffOps(
            employee_id="CNA001",
            home_unit_id="U-SA1",
            hire_date=date(2020, 6, 1),
        )
    )
    workload_db.add(
        HoursLedger(
            employee_id="CNA001",
            cycle_start_date=date(2026, 4, 27),
            hours_this_cycle=31.0,
            shift_count_this_biweek=4,
            updated_at=datetime.now(timezone.utc),
        )
    )
    for day in range(1, 6):
        workload_db.add(
            ScheduleEntry(
                employee_id="CNA001",
                unit_id="U-SA1",
                shift_date=date(2026, 5, day),
                shift_label=ModelShiftLabel.DAY,
                is_published=True,
            )
        )
    await workload_db.commit()

    snapshot = await build_work_hours_snapshot(
        workload_db,
        year=2026,
        month=5,
        timeclock_source=FakeTimeClockSource(),
        as_of=date(2026, 4, 30),
    )

    employee = snapshot.employees[0]
    assert employee.cycle_start_date == date(2026, 4, 27)
    assert employee.cycle_end_date == date(2026, 5, 10)
    assert employee.worked_hours_this_cycle == pytest.approx(31.0)
    assert employee.worked_hours_this_month == pytest.approx(0.0)
    assert employee.scheduled_hours == pytest.approx(41.25)
    assert len(employee.weekly_periods) == 5
    assert employee.weekly_periods[0].start_date == date(2026, 4, 27)
    assert employee.weekly_periods[0].end_date == date(2026, 5, 3)
    assert employee.weekly_periods[0].projected_hours == pytest.approx(24.75)
    assert len(employee.biweekly_periods) == 3
    assert employee.biweekly_periods[0].start_date == date(2026, 4, 27)
    assert employee.biweekly_periods[0].end_date == date(2026, 5, 10)
    assert employee.biweekly_periods[0].worked_hours == pytest.approx(31.0)
    assert employee.biweekly_periods[0].scheduled_hours == pytest.approx(10.25)
    assert employee.biweekly_periods[0].projected_hours == pytest.approx(41.25)
