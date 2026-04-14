from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]
from fastapi import APIRouter

from app.config import settings

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
    for section in ("weights", "thresholds", "clinical_fit_scores", "float_penalty_values"):
        if section in payload and section in current:
            current[section].update(payload[section])

    # Write back
    with open(path, "w") as f:
        yaml.dump(current, f, default_flow_style=False, sort_keys=False)

    return current
