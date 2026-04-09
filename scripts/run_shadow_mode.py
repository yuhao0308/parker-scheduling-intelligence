"""Shadow mode runner.

Replays historical call-outs through the recommendation engine and
compares what the engine would have recommended vs what actually happened.

Usage:
    python scripts/run_shadow_mode.py

Requires the app to be running (uvicorn app.main:app) and seeded with data.
"""
from __future__ import annotations

import json
import sys

import httpx

BASE_URL = "http://localhost:8000"

# Historical call-outs to replay (date, unit, shift, who_called_out, who_actually_filled)
HISTORICAL_CALLOUTS = [
    {
        "callout_employee_id": "CNA001",
        "unit_id": "U-SA1",
        "shift_date": "2026-04-09",
        "shift_label": "DAY",
        "actual_replacement": "CNA005",
        "notes": "Per diem CNA picked up — was she the best option?",
    },
    {
        "callout_employee_id": "RN001",
        "unit_id": "U-SA1",
        "shift_date": "2026-04-10",
        "shift_label": "DAY",
        "actual_replacement": "RN003",
        "notes": "Per diem RN covered — check if OT was optimal",
    },
    {
        "callout_employee_id": "CNA007",
        "unit_id": "U-LT1",
        "shift_date": "2026-04-09",
        "shift_label": "EVENING",
        "actual_replacement": "CNA009",
        "notes": "PT CNA from U-LT2 floated to U-LT1",
    },
]


def run_shadow():
    print("=" * 70)
    print("SHADOW MODE: Comparing engine recommendations vs actual decisions")
    print("=" * 70)

    for i, callout in enumerate(HISTORICAL_CALLOUTS, 1):
        actual = callout.pop("actual_replacement")
        notes = callout.pop("notes")

        print(f"\n--- Callout #{i}: {callout['callout_employee_id']} out on "
              f"{callout['unit_id']} {callout['shift_label']} {callout['shift_date']} ---")
        print(f"Notes: {notes}")

        resp = httpx.post(f"{BASE_URL}/callouts", json=callout, timeout=30.0)

        if resp.status_code != 200:
            print(f"  ERROR: {resp.status_code} — {resp.text}")
            continue

        data = resp.json()
        candidates = data["candidates"]
        filter_stats = data["filter_stats"]

        print(f"  Pool: {filter_stats['total_pool']} total, "
              f"{filter_stats['passed_filter']} passed filters")
        print(f"  Filtered out: {filter_stats['filtered_out']}")

        # Find where the actual replacement ranked
        actual_rank = None
        for c in candidates:
            if c["employee_id"] == actual:
                actual_rank = c["rank"]
                break

        print(f"\n  Engine's top 5:")
        for c in candidates[:5]:
            marker = " <-- ACTUAL" if c["employee_id"] == actual else ""
            print(f"    #{c['rank']} {c['name']} ({c['license']}) "
                  f"score={c['score']:.3f}{marker}")
            print(f"       {c['rationale']}")

        if actual_rank:
            print(f"\n  Actual replacement ({actual}) ranked #{actual_rank} by engine")
            if actual_rank == 1:
                print("  MATCH: Engine agrees with coordinator's choice")
            else:
                print(f"  OVERRIDE: Coordinator picked #{actual_rank}, not #1")
        else:
            print(f"\n  Actual replacement ({actual}) NOT in engine's list")
            print("  MISS: Engine would not have suggested this person")

    print("\n" + "=" * 70)
    print("Shadow mode complete. Review results above for model tuning signals.")


if __name__ == "__main__":
    run_shadow()
