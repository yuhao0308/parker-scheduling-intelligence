"""Seed initial unit and shift window data.

Run via: python -c "import asyncio; from app.db.seed import seed_units; asyncio.run(seed_units())"
"""
from __future__ import annotations

from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.unit import ShiftLabel, ShiftWindow, Unit, UnitTypology


UNITS = [
    # Subacute units (4)
    ("U-SA1", "Subacute Unit 1 — Post-Surgical", UnitTypology.SUBACUTE, 3.5),
    ("U-SA2", "Subacute Unit 2 — Trach/Vent", UnitTypology.SUBACUTE, 3.5),
    ("U-SA3", "Subacute Unit 3 — Complex Wound", UnitTypology.SUBACUTE, 3.5),
    ("U-SA4", "Subacute Unit 4 — Rehab", UnitTypology.SUBACUTE, 3.5),
    # Long-term units (8)
    ("U-LT1", "Long-Term Unit 1", UnitTypology.LT, 3.5),
    ("U-LT2", "Long-Term Unit 2", UnitTypology.LT, 3.5),
    ("U-LT3", "Long-Term Unit 3", UnitTypology.LT, 3.5),
    ("U-LT4", "Long-Term Unit 4", UnitTypology.LT, 3.5),
    ("U-LT5", "Long-Term Unit 5", UnitTypology.LT, 3.5),
    ("U-LT6", "Long-Term Unit 6", UnitTypology.LT, 3.5),
    ("U-LT7", "Long-Term Unit 7", UnitTypology.LT, 3.5),
    ("U-LT8", "Long-Term Unit 8", UnitTypology.LT, 3.5),
]

SHIFT_WINDOWS = [
    (ShiftLabel.NIGHT, time(23, 0), time(7, 15)),
    (ShiftLabel.DAY, time(7, 0), time(15, 15)),
    (ShiftLabel.EVENING, time(15, 0), time(23, 15)),
]


async def seed_units():
    """Create units and shift windows if they don't exist."""
    async with async_session_factory() as db:
        # Insert all units first and flush so shift_window FKs are satisfied
        # before the next iteration's autoflush tries to insert them.
        new_unit_ids: list[str] = []
        for unit_id, name, typology, ratio in UNITS:
            existing = await db.get(Unit, unit_id)
            if not existing:
                db.add(Unit(
                    unit_id=unit_id, name=name,
                    typology=typology, required_ratio=ratio,
                ))
                new_unit_ids.append(unit_id)
        await db.flush()

        for unit_id in new_unit_ids:
            for label, start, end in SHIFT_WINDOWS:
                db.add(ShiftWindow(
                    unit_id=unit_id, shift_label=label,
                    start_time=start, end_time=end,
                ))

        await db.commit()
        print(f"Seeded {len(new_unit_ids)} new units (of {len(UNITS)} total).")


if __name__ == "__main__":
    import asyncio
    asyncio.run(seed_units())
