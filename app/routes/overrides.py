from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.db.session import get_db
from app.exceptions import AppError
from app.models.recommendation import OverrideLog, RecommendationLog
from app.schemas.callout import HITLFeedbackTag, OverrideRequest, OverrideResponse
from app.schemas.common import ShiftLabel
from app.services.wfm_writeback import write_back_assignment

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

    # When the scheduler bypasses the top recommendation we require a
    # structured feedback tag. The free-text reason stays optional for
    # nuance, but the tag powers the HITL -> ML training pipeline.
    if (
        selected_rank is not None
        and selected_rank != 1
        and request.feedback_tag is None
        and not (request.override_reason and request.override_reason.strip())
    ):
        raise AppError(
            "Either a feedback_tag or a free-text override_reason is required "
            "when overriding the top recommendation.",
            status_code=400,
        )

    override = OverrideLog(
        recommendation_log_id=request.recommendation_log_id,
        selected_employee_id=request.selected_employee_id,
        selected_rank=selected_rank,
        override_reason=request.override_reason,
        feedback_tag=request.feedback_tag.value if request.feedback_tag else None,
        coordinator_id=request.coordinator_id,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(override)
    await db.commit()
    await db.refresh(override)

    # Phase 5: push the accepted replacement back into the master WFM roster.
    # Result is surfaced in the response so the UI can show sync status.
    wb_result = write_back_assignment(
        settings=app_settings,
        employee_id=request.selected_employee_id,
        unit_id=rec.target_unit_id,
        shift_date=rec.target_shift_date,
        shift_label=ShiftLabel(rec.target_shift_label.value),
        callout_id=rec.callout_id,
    )

    return OverrideResponse(
        override_id=override.id,
        recommendation_log_id=override.recommendation_log_id,
        selected_employee_id=override.selected_employee_id,
        selected_rank=override.selected_rank,
        writeback_status=wb_result.status,
        writeback_detail=wb_result.detail,
    )
