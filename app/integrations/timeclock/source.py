"""TimeClockSource abstraction with three integration modes.

A real client engagement will ship one of:
  - File drops on SFTP (CSV, fixed-width, Kronos KIE export)
  - REST/SOAP API polling (Kronos WFC, UKG Pro)
  - Direct ODBC/JDBC against vendor-provided views

All three return identical Pydantic models, so consumer code (the aggregator,
ingestion endpoints, reports) doesn't care which transport produced the data.

For the POC, all three impls read the same generated dummy CSVs in
``artifacts/timeclock/``. The API and DB variants exist so we can demo the
integration shape without standing up a fake Kronos server. The simulated
latency is an honest reminder that real network/db hops are not free.
"""

from __future__ import annotations

import asyncio
import csv
from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path

from app.integrations.timeclock.kronos_schema import (
    KronosDailyTotal,
    KronosPayPeriodSummary,
    KronosPunchRecord,
    PayCode,
    PunchDirection,
    PunchSource,
    PunchType,
)

DEFAULT_ARTIFACTS_DIR = (
    Path(__file__).resolve().parents[3] / "artifacts" / "timeclock"
)

PUNCHES_FILE = "punches.csv"
DAILY_TOTALS_FILE = "daily_totals.csv"
PAY_PERIOD_FILE = "pay_period_summary.csv"


class TimeClockSource(ABC):
    """Read-only data source for time clock punches and totals.

    Implementations should be idempotent — calling ``fetch_punches`` twice
    with the same date range must return the same records (modulo any new
    punches that landed in between).
    """

    @abstractmethod
    async def fetch_punches(
        self, start_date: date, end_date: date
    ) -> list[KronosPunchRecord]:
        """Return punch events with ``punch_datetime`` in [start_date, end_date]."""

    @abstractmethod
    async def fetch_daily_totals(
        self, start_date: date, end_date: date
    ) -> list[KronosDailyTotal]:
        """Return daily totals for ``work_date`` in [start_date, end_date]."""

    @abstractmethod
    async def fetch_pay_period_summary(
        self, period_start: date
    ) -> list[KronosPayPeriodSummary]:
        """Return the biweekly summary for the cycle starting on ``period_start``."""


class CSVSource(TimeClockSource):
    """Read Kronos WIM-format CSV exports from disk.

    This is the most common real-world integration mode for long-term-care
    facilities — the time clock vendor SFTPs nightly exports to a known path
    and the consumer reads them on a cron.
    """

    def __init__(self, artifacts_dir: Path | None = None) -> None:
        self.artifacts_dir = Path(artifacts_dir) if artifacts_dir else DEFAULT_ARTIFACTS_DIR

    async def fetch_punches(
        self, start_date: date, end_date: date
    ) -> list[KronosPunchRecord]:
        rows = await asyncio.to_thread(
            _read_csv, self.artifacts_dir / PUNCHES_FILE
        )
        out: list[KronosPunchRecord] = []
        for row in rows:
            ts = datetime.fromisoformat(row["punch_datetime"])
            if not (start_date <= ts.date() <= end_date):
                continue
            out.append(
                KronosPunchRecord(
                    person_number=row["person_number"],
                    person_name=row["person_name"],
                    punch_datetime=ts,
                    direction=PunchDirection(row["direction"]),
                    punch_type=PunchType(row["punch_type"]),
                    labor_level_1=row["labor_level_1"],
                    labor_level_2=row["labor_level_2"],
                    labor_level_3=row["labor_level_3"],
                    pay_code=PayCode(row["pay_code"]),
                    source=PunchSource(row["source"]),
                    terminal_id=row["terminal_id"] or None,
                    edited=row["edited"].lower() == "true",
                    edit_user=row["edit_user"] or None,
                    edit_reason=row["edit_reason"] or None,
                    override=row["override"] or None,
                )
            )
        return out

    async def fetch_daily_totals(
        self, start_date: date, end_date: date
    ) -> list[KronosDailyTotal]:
        rows = await asyncio.to_thread(
            _read_csv, self.artifacts_dir / DAILY_TOTALS_FILE
        )
        out: list[KronosDailyTotal] = []
        for row in rows:
            wd = date.fromisoformat(row["work_date"])
            if not (start_date <= wd <= end_date):
                continue
            out.append(
                KronosDailyTotal(
                    person_number=row["person_number"],
                    work_date=wd,
                    pay_code=PayCode(row["pay_code"]),
                    hours=float(row["hours"]),
                    job=row["job"],
                    labor_level_1=row["labor_level_1"],
                    labor_level_2=row["labor_level_2"],
                    labor_level_3=row["labor_level_3"],
                    shift_count=int(row["shift_count"]),
                )
            )
        return out

    async def fetch_pay_period_summary(
        self, period_start: date
    ) -> list[KronosPayPeriodSummary]:
        rows = await asyncio.to_thread(
            _read_csv, self.artifacts_dir / PAY_PERIOD_FILE
        )
        out: list[KronosPayPeriodSummary] = []
        for row in rows:
            if date.fromisoformat(row["pay_period_start"]) != period_start:
                continue
            out.append(
                KronosPayPeriodSummary(
                    person_number=row["person_number"],
                    pay_period_start=date.fromisoformat(row["pay_period_start"]),
                    pay_period_end=date.fromisoformat(row["pay_period_end"]),
                    regular_hours=float(row["regular_hours"]),
                    overtime_hours=float(row["overtime_hours"]),
                    doubletime_hours=float(row["doubletime_hours"]),
                    holiday_hours=float(row["holiday_hours"]),
                    sick_hours=float(row["sick_hours"]),
                    pto_hours=float(row["pto_hours"]),
                    shift_count=int(row["shift_count"]),
                    missed_punch_count=int(row["missed_punch_count"]),
                )
            )
        return out


class APISource(TimeClockSource):
    """Simulate a REST API integration (Kronos WFC / UKG Pro shape).

    A real implementation would issue HTTP calls and page through results.
    For the POC, this delegates to ``CSVSource`` after a small sleep so that
    demos correctly model that API access is not free.
    """

    def __init__(
        self,
        backing: CSVSource | None = None,
        simulated_latency_ms: int = 150,
    ) -> None:
        self._backing = backing or CSVSource()
        self._latency_s = simulated_latency_ms / 1000.0

    async def fetch_punches(self, start_date, end_date):
        await asyncio.sleep(self._latency_s)
        return await self._backing.fetch_punches(start_date, end_date)

    async def fetch_daily_totals(self, start_date, end_date):
        await asyncio.sleep(self._latency_s)
        return await self._backing.fetch_daily_totals(start_date, end_date)

    async def fetch_pay_period_summary(self, period_start):
        await asyncio.sleep(self._latency_s)
        return await self._backing.fetch_pay_period_summary(period_start)


class DBSource(TimeClockSource):
    """Simulate direct ODBC/JDBC access to vendor-provided views.

    Some clients expose Kronos data as SQL views the consumer can query
    directly. This impl is a stub for demo purposes; in production it would
    issue parameterized queries against ``vw_punch_detail``,
    ``vw_daily_totals``, etc.
    """

    def __init__(
        self,
        backing: CSVSource | None = None,
        simulated_latency_ms: int = 25,
    ) -> None:
        self._backing = backing or CSVSource()
        self._latency_s = simulated_latency_ms / 1000.0

    async def fetch_punches(self, start_date, end_date):
        await asyncio.sleep(self._latency_s)
        return await self._backing.fetch_punches(start_date, end_date)

    async def fetch_daily_totals(self, start_date, end_date):
        await asyncio.sleep(self._latency_s)
        return await self._backing.fetch_daily_totals(start_date, end_date)

    async def fetch_pay_period_summary(self, period_start):
        await asyncio.sleep(self._latency_s)
        return await self._backing.fetch_pay_period_summary(period_start)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(
            f"Time clock CSV not found at {path}. "
            "Run scripts/generate_timeclock_data.py to create dummy data."
        )
    with path.open(newline="") as f:
        return list(csv.DictReader(f))
