"""Bridge from Kronos pay-period summaries into the internal HoursLedger.

The time clock layer (``app.integrations.timeclock``) emits
``KronosPayPeriodSummary`` rows — biweekly roll-ups of REG/OT/PTO/SICK hours
plus a shift count and missed-punch flag. The internal scoring engine reads
worked hours from ``HoursLedger`` (employee × cycle_start_date). This module
is the adapter between the two.

Key design choices:
  - Reads via a ``TimeClockSource`` (CSV in the demo, REST/DB in production).
    Adding a new source mode requires no changes here.
  - "Worked hours" excludes PTO/SICK/BEREAVE — it's time on the floor only.
    This matches the supervisor's framing ("actual working hour") and aligns
    with how OnShift / UKG render the same workload bar. PTO time still
    counts toward an employee's pay, but doesn't fill the green segment.
  - Idempotent. Re-running the ingest with the same source data produces
    the same ledger state — safe to wire into a cron or to demo repeatedly.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.timeclock.kronos_schema import KronosPayPeriodSummary
from app.integrations.timeclock.source import TimeClockSource
from app.schemas.schedule import HoursLedgerSyncRecord
from app.schemas.staff import SyncResult
from app.services.data_sync import sync_hours


def summary_to_ledger_record(
    summary: KronosPayPeriodSummary,
) -> HoursLedgerSyncRecord:
    """Convert a Kronos biweekly roll-up into the internal HoursLedger shape.

    Worked hours = REG + OT + DT + HOL. PTO and SICK are deliberately
    excluded so the workload bar shows time on the floor, not total paid
    time. If a future requirement needs total paid time, prefer adding a
    second derived field rather than redefining this one.
    """
    worked_hours = (
        summary.regular_hours
        + summary.overtime_hours
        + summary.doubletime_hours
        + summary.holiday_hours
    )
    return HoursLedgerSyncRecord(
        employee_id=summary.person_number,
        cycle_start_date=summary.pay_period_start,
        hours_this_cycle=round(worked_hours, 2),
        shift_count_this_biweek=summary.shift_count,
    )


async def ingest_pay_period_summaries(
    db: AsyncSession,
    source: TimeClockSource,
    period_starts: list[date],
) -> SyncResult:
    """Pull biweekly summaries from ``source`` and upsert them into HoursLedger.

    Each entry in ``period_starts`` triggers one ``fetch_pay_period_summary``
    call. The aggregator's per-cycle output is the unit of work — we don't
    re-aggregate raw punches in the request path.

    Returns the cumulative SyncResult (created + updated + total) across all
    requested periods.
    """
    all_records: list[HoursLedgerSyncRecord] = []
    for period_start in period_starts:
        summaries = await source.fetch_pay_period_summary(period_start)
        all_records.extend(summary_to_ledger_record(s) for s in summaries)

    if not all_records:
        return SyncResult(created=0, updated=0, total=0)

    return await sync_hours(all_records, db)
