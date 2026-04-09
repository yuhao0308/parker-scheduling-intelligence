from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.exceptions import AppError
from app.models.recommendation import OverrideLog, RecommendationLog
from app.schemas.callout import OverrideRequest, OverrideResponse

router = APIRouter(tags=["overrides"])


@router.post("/overrides", response_model=OverrideResponse)
async def record_override(
    request: OverrideRequest,
    db: AsyncSession = Depends(get_db),
) -> OverrideResponse:
    """Log which candidate the coordinator actually picked."""
    # Verify the recommendation exists
    rec = await db.get(RecommendationLog, request.recommendation_log_id)
    if not rec:
        raise AppError(
            f"Recommendation log {request.recommendation_log_id} not found",
            status_code=404,
        )

    # Determine the rank of the selected candidate (if they were in the list)
    selected_rank = None
    if rec.ranked_candidates:
        for cand in rec.ranked_candidates:
            if cand.get("employee_id") == request.selected_employee_id:
                selected_rank = cand.get("rank")
                break

    override = OverrideLog(
        recommendation_log_id=request.recommendation_log_id,
        selected_employee_id=request.selected_employee_id,
        selected_rank=selected_rank,
        override_reason=request.override_reason,
        coordinator_id=request.coordinator_id,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(override)
    await db.commit()
    await db.refresh(override)

    return OverrideResponse(
        override_id=override.id,
        recommendation_log_id=override.recommendation_log_id,
        selected_employee_id=override.selected_employee_id,
        selected_rank=override.selected_rank,
    )
