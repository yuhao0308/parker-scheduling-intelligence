from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.models.notification import SimulatedNotification
from app.models.recommendation import OverrideLog, RecommendationLog
from app.models.schedule import Callout, ScheduleEntry

router = APIRouter(prefix="/config", tags=["admin"])


@router.get("/weights")
async def get_weights() -> dict:
    """Return current scoring weights and thresholds."""
    with open(settings.scoring_weights_path) as f:
        return yaml.safe_load(f)


@router.put("/weights")
async def update_weights(payload: dict) -> dict:
    """Update scoring weights at runtime. Writes back to YAML."""
    # Load current config
    path = settings.scoring_weights_path
    with open(path) as f:
        current = yaml.safe_load(f)

    # Merge updates (only update keys that exist)
    for section in (
        "weights",
        "thresholds",
        "clinical_fit_scores",
        "float_penalty_values",
        "ot_warning_thresholds",
    ):
        if section in payload and section in current:
            current[section].update(payload[section])

    # Write back
    with open(path, "w") as f:
        yaml.dump(current, f, default_flow_style=False, sort_keys=False)

    return current


@router.post("/reset-calendar", summary="Demo-only: wipe all scheduled shifts")
async def reset_calendar(db: AsyncSession = Depends(get_db)) -> dict:
    """Delete every schedule entry, callout, and dependent log row.

    Demo-only reset: leaves staff/units/weights intact so the supervisor can
    rebuild a fresh month from the Auto-Gen panel.
    """
    # Break the ScheduleEntry self-FK before deletion.
    await db.execute(
        update(ScheduleEntry).values(replaced_by_entry_id=None)
    )
    await db.execute(delete(SimulatedNotification))
    await db.execute(delete(OverrideLog))
    await db.execute(delete(RecommendationLog))
    await db.execute(delete(Callout))
    result = await db.execute(delete(ScheduleEntry))
    await db.commit()
    return {"entries_deleted": result.rowcount or 0}
