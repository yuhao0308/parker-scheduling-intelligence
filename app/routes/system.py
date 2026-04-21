"""System/config endpoints exposed to the frontend."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(tags=["system"])


class DemoConfigOut(BaseModel):
    demo_mode: bool
    confirmation_timeout_s: int
    confirmation_timeout_label: str
    outreach_timeout_s: int
    outreach_timeout_label: str


@router.get(
    "/config/demo",
    response_model=DemoConfigOut,
    summary="Return enforced timer values + display labels for the UI",
    description=(
        "The UI reads this once on boot. `_seconds` fields drive countdown "
        "enforcement; `_label` fields drive the human-readable display so the "
        "demo can tick in 15s while the UI truthfully says '2 hours' / '15 minutes'."
    ),
)
async def get_demo_config() -> DemoConfigOut:
    return DemoConfigOut(
        demo_mode=settings.demo_mode,
        confirmation_timeout_s=settings.confirmation_timeout_seconds,
        confirmation_timeout_label=settings.confirmation_timeout_label,
        outreach_timeout_s=settings.outreach_timeout_seconds,
        outreach_timeout_label=settings.outreach_timeout_label,
    )
