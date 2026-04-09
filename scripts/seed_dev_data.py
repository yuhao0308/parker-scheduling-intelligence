"""Seed the database with realistic Parker test data.

Creates 12 units (4 subacute, 8 LT), ~30 staff, 1 week of schedule,
hours ledger entries, and a few exclusions. Run against a local DB.

Usage:
    python scripts/seed_dev_data.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone

import httpx

BASE_URL = "http://localhost:8000"


def seed_units():
    """Seed units via a direct approach (no sync endpoint for units yet)."""
    print("Note: Units must be created directly in DB or via migration seed.")
    print("Skipping unit creation — use Alembic seed or manual insert.")


def seed_staff():
    """Seed ~30 staff members with varied profiles."""
    staff = [
        # Subacute RNs
        {"employee_id": "RN001", "name": "Maria Rodriguez", "license": "RN", "employment_class": "FT", "zip_code": "11375", "home_unit_id": "U-SA1", "cross_trained_units": ["U-SA2"], "hire_date": "2019-03-15"},
        {"employee_id": "RN002", "name": "James Thompson", "license": "RN", "employment_class": "PT", "zip_code": "10301", "home_unit_id": "U-SA2", "cross_trained_units": ["U-SA1"], "hire_date": "2017-06-01"},
        {"employee_id": "RN003", "name": "Priya Patel", "license": "RN", "employment_class": "PER_DIEM", "zip_code": "11432", "home_unit_id": "U-SA1", "cross_trained_units": [], "hire_date": "2020-09-01"},
        {"employee_id": "RN004", "name": "Carlos Mendez", "license": "RN", "employment_class": "FT", "zip_code": "07030", "home_unit_id": "U-SA3", "cross_trained_units": ["U-SA1", "U-SA2"], "hire_date": "2015-01-10"},
        # LT RNs
        {"employee_id": "RN005", "name": "Lisa Chen", "license": "RN", "employment_class": "FT", "zip_code": "11375", "home_unit_id": "U-LT1", "cross_trained_units": [], "hire_date": "2021-02-15"},
        {"employee_id": "RN006", "name": "Robert Williams", "license": "RN", "employment_class": "PT", "zip_code": "11432", "home_unit_id": "U-LT2", "cross_trained_units": ["U-LT1"], "hire_date": "2018-11-01"},
        # LPNs
        {"employee_id": "LPN001", "name": "Sarah Kim", "license": "LPN", "employment_class": "FT", "zip_code": "11375", "home_unit_id": "U-LT3", "cross_trained_units": ["U-LT1", "U-LT2"], "hire_date": "2018-09-01"},
        {"employee_id": "LPN002", "name": "Angela Davis", "license": "LPN", "employment_class": "PER_DIEM", "zip_code": "10301", "home_unit_id": "U-LT4", "cross_trained_units": [], "hire_date": "2022-05-15"},
        {"employee_id": "LPN003", "name": "Mark Johnson", "license": "LPN", "employment_class": "FT", "zip_code": "07030", "home_unit_id": "U-SA4", "cross_trained_units": ["U-SA1"], "hire_date": "2019-07-01"},
        # Subacute CNAs
        {"employee_id": "CNA001", "name": "Aisha Johnson", "license": "CNA", "employment_class": "FT", "zip_code": "11375", "home_unit_id": "U-SA1", "cross_trained_units": ["U-SA2", "U-LT1"], "hire_date": "2020-06-01"},
        {"employee_id": "CNA002", "name": "David Brown", "license": "CNA", "employment_class": "FT", "zip_code": "11375", "home_unit_id": "U-SA1", "cross_trained_units": [], "hire_date": "2019-01-15"},
        {"employee_id": "CNA003", "name": "Fatima Ali", "license": "CNA", "employment_class": "FT", "zip_code": "11432", "home_unit_id": "U-SA2", "cross_trained_units": ["U-SA1"], "hire_date": "2021-03-01"},
        {"employee_id": "CNA004", "name": "Mike Smith", "license": "CNA", "employment_class": "PT", "zip_code": "10301", "home_unit_id": "U-SA2", "cross_trained_units": [], "hire_date": "2023-11-01"},
        {"employee_id": "CNA005", "name": "Jennifer Garcia", "license": "CNA", "employment_class": "PER_DIEM", "zip_code": "11375", "home_unit_id": "U-SA3", "cross_trained_units": ["U-SA1", "U-SA2"], "hire_date": "2018-04-15"},
        {"employee_id": "CNA006", "name": "Omar Hassan", "license": "CNA", "employment_class": "FT", "zip_code": "07030", "home_unit_id": "U-SA4", "cross_trained_units": [], "hire_date": "2025-12-01"},
        # LT CNAs
        {"employee_id": "CNA007", "name": "Patricia Lee", "license": "CNA", "employment_class": "FT", "zip_code": "11375", "home_unit_id": "U-LT1", "cross_trained_units": ["U-LT2"], "hire_date": "2019-08-01"},
        {"employee_id": "CNA008", "name": "William Taylor", "license": "CNA", "employment_class": "FT", "zip_code": "11432", "home_unit_id": "U-LT1", "cross_trained_units": [], "hire_date": "2020-12-15"},
        {"employee_id": "CNA009", "name": "Rosa Martinez", "license": "CNA", "employment_class": "PT", "zip_code": "11375", "home_unit_id": "U-LT2", "cross_trained_units": ["U-LT1", "U-LT3"], "hire_date": "2017-05-01"},
        {"employee_id": "CNA010", "name": "Kevin Nguyen", "license": "CNA", "employment_class": "FT", "zip_code": "10301", "home_unit_id": "U-LT2", "cross_trained_units": [], "hire_date": "2022-02-01"},
        {"employee_id": "CNA011", "name": "Diana Wilson", "license": "CNA", "employment_class": "FT", "zip_code": "11375", "home_unit_id": "U-LT3", "cross_trained_units": ["U-LT4"], "hire_date": "2021-06-15"},
        {"employee_id": "CNA012", "name": "Brian Clark", "license": "CNA", "employment_class": "PER_DIEM", "zip_code": "07030", "home_unit_id": "U-LT3", "cross_trained_units": [], "hire_date": "2023-01-01"},
        {"employee_id": "CNA013", "name": "Maria Santos", "license": "CNA", "employment_class": "FT", "zip_code": "11432", "home_unit_id": "U-LT4", "cross_trained_units": ["U-LT3"], "hire_date": "2018-10-01"},
        {"employee_id": "CNA014", "name": "Thomas Anderson", "license": "CNA", "employment_class": "FT", "zip_code": "11375", "home_unit_id": "U-LT4", "cross_trained_units": [], "hire_date": "2024-03-15"},
        {"employee_id": "CNA015", "name": "Grace Park", "license": "CNA", "employment_class": "PT", "zip_code": "11375", "home_unit_id": "U-LT5", "cross_trained_units": ["U-LT4"], "hire_date": "2020-01-01"},
        # PCTs
        {"employee_id": "PCT001", "name": "Ahmad Ibrahim", "license": "PCT", "employment_class": "FT", "zip_code": "11375", "home_unit_id": "U-SA1", "cross_trained_units": ["U-SA2"], "hire_date": "2021-09-01"},
        {"employee_id": "PCT002", "name": "Nicole Brown", "license": "PCT", "employment_class": "FT", "zip_code": "11432", "home_unit_id": "U-LT5", "cross_trained_units": [], "hire_date": "2022-07-15"},
    ]

    resp = httpx.post(f"{BASE_URL}/sync/staff", json={"records": staff})
    print(f"Staff sync: {resp.status_code} — {resp.json()}")


def seed_schedule():
    """Seed a week of schedule entries."""
    entries = []
    shifts = ["DAY", "EVENING", "NIGHT"]

    # Staff scheduled for the week of Apr 7-11, 2026
    schedule_map = {
        # Subacute units — heavier staffing
        "U-SA1": {"DAY": ["RN001", "CNA001", "CNA002", "PCT001"], "EVENING": ["RN003", "CNA001", "CNA005"], "NIGHT": ["RN001", "CNA002"]},
        "U-SA2": {"DAY": ["RN002", "CNA003", "CNA004"], "EVENING": ["RN002", "CNA003"], "NIGHT": ["RN004", "CNA004"]},
        # LT units
        "U-LT1": {"DAY": ["RN005", "CNA007", "CNA008"], "EVENING": ["LPN001", "CNA007"], "NIGHT": ["RN005", "CNA008"]},
        "U-LT2": {"DAY": ["RN006", "CNA009", "CNA010"], "EVENING": ["RN006", "CNA009"], "NIGHT": ["LPN001", "CNA010"]},
    }

    for d in range(7, 12):  # Apr 7-11
        shift_date = f"2026-04-{d:02d}"
        for unit_id, shift_staff in schedule_map.items():
            for shift_label, emp_ids in shift_staff.items():
                for emp_id in emp_ids:
                    entries.append({
                        "employee_id": emp_id,
                        "unit_id": unit_id,
                        "shift_date": shift_date,
                        "shift_label": shift_label,
                        "is_published": True,
                    })

    resp = httpx.post(f"{BASE_URL}/sync/schedule", json={"schedule_entries": entries})
    print(f"Schedule sync: {resp.status_code} — {resp.json()}")


def seed_hours():
    """Seed hours ledger for the current pay cycle."""
    records = [
        # CNAs with varied hours
        {"employee_id": "CNA001", "cycle_start_date": "2026-04-06", "hours_this_cycle": 24.75, "shift_count_this_biweek": 3},
        {"employee_id": "CNA002", "cycle_start_date": "2026-04-06", "hours_this_cycle": 33.0, "shift_count_this_biweek": 4},
        {"employee_id": "CNA003", "cycle_start_date": "2026-04-06", "hours_this_cycle": 16.5, "shift_count_this_biweek": 2},
        {"employee_id": "CNA004", "cycle_start_date": "2026-04-06", "hours_this_cycle": 8.25, "shift_count_this_biweek": 1},
        {"employee_id": "CNA005", "cycle_start_date": "2026-04-06", "hours_this_cycle": 0.0, "shift_count_this_biweek": 0},
        {"employee_id": "CNA006", "cycle_start_date": "2026-04-06", "hours_this_cycle": 0.0, "shift_count_this_biweek": 0},
        {"employee_id": "CNA007", "cycle_start_date": "2026-04-06", "hours_this_cycle": 24.75, "shift_count_this_biweek": 3},
        {"employee_id": "CNA008", "cycle_start_date": "2026-04-06", "hours_this_cycle": 24.75, "shift_count_this_biweek": 3},
        {"employee_id": "CNA009", "cycle_start_date": "2026-04-06", "hours_this_cycle": 16.5, "shift_count_this_biweek": 2},
        {"employee_id": "CNA010", "cycle_start_date": "2026-04-06", "hours_this_cycle": 24.75, "shift_count_this_biweek": 3},
        {"employee_id": "PCT001", "cycle_start_date": "2026-04-06", "hours_this_cycle": 24.75, "shift_count_this_biweek": 3},
        # RNs with biweekly tracking
        {"employee_id": "RN001", "cycle_start_date": "2026-03-30", "hours_this_cycle": 66.0, "shift_count_this_biweek": 8},
        {"employee_id": "RN002", "cycle_start_date": "2026-03-30", "hours_this_cycle": 49.5, "shift_count_this_biweek": 6},
        {"employee_id": "RN003", "cycle_start_date": "2026-03-30", "hours_this_cycle": 16.5, "shift_count_this_biweek": 2},
        {"employee_id": "RN004", "cycle_start_date": "2026-03-30", "hours_this_cycle": 74.25, "shift_count_this_biweek": 9},
        {"employee_id": "RN005", "cycle_start_date": "2026-03-30", "hours_this_cycle": 57.75, "shift_count_this_biweek": 7},
        {"employee_id": "RN006", "cycle_start_date": "2026-03-30", "hours_this_cycle": 41.25, "shift_count_this_biweek": 5},
        {"employee_id": "LPN001", "cycle_start_date": "2026-04-06", "hours_this_cycle": 33.0, "shift_count_this_biweek": 4},
    ]

    resp = httpx.post(f"{BASE_URL}/sync/hours", json={"records": records})
    print(f"Hours sync: {resp.status_code} — {resp.json()}")


def test_callout():
    """Simulate a call-out and get recommendations."""
    print("\n--- Simulating CNA call-out on U-SA1 DAY shift ---")
    resp = httpx.post(
        f"{BASE_URL}/callouts",
        json={
            "callout_employee_id": "CNA001",
            "unit_id": "U-SA1",
            "shift_date": "2026-04-09",
            "shift_label": "DAY",
        },
        timeout=30.0,
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f"Callout ID: {data['callout_id']}")
        print(f"Filter stats: {data['filter_stats']}")
        print(f"Top candidates:")
        for c in data["candidates"][:5]:
            print(f"  #{c['rank']} {c['name']} ({c['license']}) — score {c['score']:.3f}")
            print(f"     {c['rationale']}")
    else:
        print(f"Error: {resp.status_code} — {resp.text}")


if __name__ == "__main__":
    print(f"Seeding against {BASE_URL}")
    seed_staff()
    seed_schedule()
    seed_hours()
    if "--test" in sys.argv:
        test_callout()
    print("\nDone!")
