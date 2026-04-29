"""Time clock integration layer.

The POC consumes punch + totals data from the client's existing time clock
system (typically Kronos/UKG WIM, ADP, or SmartLinx Time). We never own the
clock-in/out flow — we read what's already there and aggregate it for
workload, hours tracking, and overtime calculations.

Three integration modes are supported behind a single ``TimeClockSource``
interface so the consumer doesn't care how data arrives:

- ``CSVSource``  — scheduled file exports (the long-term-care default)
- ``APISource``  — REST/SOAP polling (Kronos WFC, UKG Pro)
- ``DBSource``   — direct read against vendor-provided views

For the POC, all three impls read the same generated dummy CSVs in
``artifacts/timeclock/``; the API and DB variants just simulate transport so
demos can show the integration shape without standing up a fake server.

The schema mirrors Kronos WIM (punch + daily totals + pay-period summary) so
that swapping in a real client extract is a column-rename exercise, not a
rewrite.
"""

from app.integrations.timeclock.kronos_schema import (
    KronosDailyTotal,
    KronosPayPeriodSummary,
    KronosPunchRecord,
)
from app.integrations.timeclock.source import (
    APISource,
    CSVSource,
    DBSource,
    TimeClockSource,
)

__all__ = [
    "APISource",
    "CSVSource",
    "DBSource",
    "KronosDailyTotal",
    "KronosPayPeriodSummary",
    "KronosPunchRecord",
    "TimeClockSource",
]
