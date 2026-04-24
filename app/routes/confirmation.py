"""Confirmation flow routes for the scheduler-side weekly confirm demo."""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.schemas.confirmation import (
    CommitMonthlyDecisionsRequest,
    CommitDecisionsRequest,
    CommitDecisionsResult,
    ConfirmationListOut,
    RemoveEntryResult,
    RespondConfirmationRequest,
    RespondConfirmationResult,
    ReplaceEntryRequest,
    ReplaceEntryResult,
    SendConfirmationsRequest,
    SendConfirmationsResult,
    SendMonthlyConfirmationsRequest,
    TimeoutSweepRequest,
    TimeoutSweepResult,
)
from app.services.confirmation import (
    commit_month_decisions,
    commit_week_decisions,
    list_month_confirmations,
    list_week_confirmations,
    remove_entry,
    replace_declined_entry,
    respond_to_confirmation,
    send_month_confirmations,
    send_week_confirmations,
    timeout_sweep_entries,
)

router = APIRouter(tags=["confirmations"])

# Hardcoded for the demo — no auth layer; in prod this comes from session.
DEMO_COORDINATOR_ID = "demo-scheduler"


@router.post(
    "/schedule/confirmations/send",
    response_model=SendConfirmationsResult,
    summary="Send weekly shift confirmations to assigned nurses",
)
async def send_confirmations(
    req: SendConfirmationsRequest,
    db: AsyncSession = Depends(get_db),
) -> SendConfirmationsResult:
    return await send_week_confirmations(db, req.week_start, req.unit_ids)


@router.post(
    "/schedule/confirmations/send-month",
    response_model=SendConfirmationsResult,
    summary="Send monthly shift confirmations to assigned nurses",
)
async def send_monthly_confirmations(
    req: SendMonthlyConfirmationsRequest,
    db: AsyncSession = Depends(get_db),
) -> SendConfirmationsResult:
    return await send_month_confirmations(db, req.year, req.month, req.unit_ids)


@router.get(
    "/schedule/confirmations",
    response_model=ConfirmationListOut,
    summary="List confirmation state for a week",
)
async def list_confirmations(
    week_start: date = Query(...),
    unit_ids: Optional[List[str]] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ConfirmationListOut:
    return await list_week_confirmations(db, week_start, unit_ids)


@router.get(
    "/schedule/confirmations/monthly",
    response_model=ConfirmationListOut,
    summary="List confirmation state for a month",
)
async def list_monthly_confirmations(
    year: int = Query(...),
    month: int = Query(...),
    unit_ids: Optional[List[str]] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> ConfirmationListOut:
    return await list_month_confirmations(db, year, month, unit_ids)


@router.post(
    "/schedule/confirmations/commit",
    response_model=CommitDecisionsResult,
    summary="Bulk-commit scheduler Accept/Decline decisions for the week",
    description=(
        "Applies all reviewed Auto-Gen decisions in one pass. Checked shifts are "
        "accepted, unchecked shifts are declined, and any declined gaps are "
        "re-rolled once against the remaining employee pool."
    ),
)
async def commit_confirmations(
    req: CommitDecisionsRequest,
    db: AsyncSession = Depends(get_db),
) -> CommitDecisionsResult:
    return await commit_week_decisions(
        db=db,
        week_start=req.week_start,
        decisions=req.decisions,
        employee_pool=req.employee_pool,
        settings=settings,
    )


@router.post(
    "/schedule/confirmations/commit-month",
    response_model=CommitDecisionsResult,
    summary="Bulk-commit scheduler Accept/Decline decisions for the month",
    description=(
        "Applies all reviewed monthly Auto-Gen decisions in one pass. Checked "
        "shifts are accepted, unchecked shifts are declined, and any declined "
        "gaps are re-rolled once against the remaining employee pool."
    ),
)
async def commit_monthly_confirmations(
    req: CommitMonthlyDecisionsRequest,
    db: AsyncSession = Depends(get_db),
) -> CommitDecisionsResult:
    return await commit_month_decisions(
        db=db,
        year=req.year,
        month=req.month,
        decisions=req.decisions,
        employee_pool=req.employee_pool,
        settings=settings,
    )


@router.post(
    "/schedule/confirmations/{entry_id}/respond",
    response_model=RespondConfirmationResult,
    summary="Record an Accept/Decline/Timeout response for a shift assignment",
)
async def respond_confirmation(
    entry_id: int,
    req: RespondConfirmationRequest,
    db: AsyncSession = Depends(get_db),
) -> RespondConfirmationResult:
    return await respond_to_confirmation(db, entry_id, req.response, settings)


@router.post(
    "/schedule/confirmations/{entry_id}/replace",
    response_model=ReplaceEntryResult,
    summary="Assign a replacement for a declined shift",
)
async def replace_entry(
    entry_id: int,
    req: ReplaceEntryRequest,
    db: AsyncSession = Depends(get_db),
) -> ReplaceEntryResult:
    return await replace_declined_entry(
        db=db,
        entry_id=entry_id,
        recommendation_log_id=req.recommendation_log_id,
        selected_employee_id=req.selected_employee_id,
        selected_rank=req.selected_rank,
        coordinator_id=DEMO_COORDINATOR_ID,
    )


@router.post(
    "/schedule/confirmations/{entry_id}/remove",
    response_model=RemoveEntryResult,
    summary="Manually drop a nurse from a slot so it can be refilled via Auto-Gen",
    description=(
        "Marks the entry REPLACED (no replacement chosen yet) and cancels the "
        "outstanding confirmation notification. The slot becomes open for the "
        "scheduler to refill by unchecking/checking pool members and re-submitting."
    ),
)
async def remove_confirmation_entry(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
) -> RemoveEntryResult:
    return await remove_entry(db=db, entry_id=entry_id)


@router.post(
    "/schedule/confirmations/timeout-sweep",
    response_model=TimeoutSweepResult,
    summary="Bulk-transition expired PENDING entries to DECLINED",
    description=(
        "Accepts a list of entry_ids that the UI has observed as expired "
        "(sent_at + confirmation_timeout_seconds < now). Non-PENDING entries "
        "are reported in `skipped` rather than raising, since races with manual "
        "Accept/Decline clicks are expected during a sweep. Does NOT generate "
        "replacement recommendations — supervisors resolve timed-out rows one "
        "at a time from the Auto-Gen panel."
    ),
)
async def timeout_sweep(
    req: TimeoutSweepRequest,
    db: AsyncSession = Depends(get_db),
) -> TimeoutSweepResult:
    return await timeout_sweep_entries(db=db, entry_ids=req.entry_ids)
