from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.db.session import get_db
from app.models.schedule import Callout
from app.schemas.callout import CalloutRequest, CalloutResponse
from app.services.recommendation import generate_recommendations

router = APIRouter(tags=["callout"])


@router.post(
    "/callouts",
    response_model=CalloutResponse,
    summary="Report a callout and rank replacement candidates",
    description=(
        "Creates a callout record, runs the recommendation pipeline, and returns "
        "ranked candidates with scoring details and filter statistics."
    ),
)
async def create_callout(
    request: CalloutRequest,
    db: AsyncSession = Depends(get_db),
) -> CalloutResponse:
    """Report a call-out and get ranked replacement candidates."""
    # Create the callout record
    callout = Callout(
        employee_id=request.callout_employee_id,
        unit_id=request.unit_id,
        shift_date=request.shift_date,
        shift_label=request.shift_label,
        reported_at=datetime.now(timezone.utc),
    )
    db.add(callout)
    await db.flush()  # get the callout ID

    # Run the recommendation pipeline
    response = await generate_recommendations(
        callout=request,
        callout_id=callout.id,
        db=db,
        settings=settings,
    )

    await db.commit()
    return response
