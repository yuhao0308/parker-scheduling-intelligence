"""WFM (UKG / SmartLinx) write-back client.

Phase-5 deliverable: push an accepted replacement assignment back into the
master roster so the call-out loop closes end-to-end. This is a thin,
dependency-free client that:

  1. Obtains an OAuth 2.0 client-credentials bearer token from the configured
     token endpoint.
  2. Issues a ``PATCH /schedule/multi-update`` (UKG Pro WFM shape) with the
     selected employee, shift, and unit payload.

When ``ukg_write_back_enabled`` is False we short-circuit and return a
"simulated" response — useful for POC environments where the real UKG hub is
not reachable. The API shape is preserved so the UI can ship today.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.config import Settings
from app.schemas.common import ShiftLabel

logger = logging.getLogger(__name__)


@dataclass
class WriteBackResult:
    status: str  # "applied" | "simulated" | "error"
    external_ref: str | None
    detail: str


def _fetch_bearer_token(settings: Settings) -> str:
    """OAuth 2.0 client_credentials grant against the WFM token endpoint."""
    data = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": settings.ukg_client_id,
            "client_secret": settings.ukg_client_secret,
        }
    ).encode("ascii")
    req = urllib.request.Request(
        settings.ukg_token_endpoint,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["access_token"]


def write_back_assignment(
    settings: Settings,
    employee_id: str,
    unit_id: str,
    shift_date: date,
    shift_label: ShiftLabel,
    callout_id: int,
) -> WriteBackResult:
    """Push an accepted replacement back into the master WFM roster."""
    if not settings.ukg_write_back_enabled:
        logger.info(
            "wfm_writeback_simulated",
            extra={
                "employee_id": employee_id,
                "unit_id": unit_id,
                "shift_date": str(shift_date),
                "shift_label": shift_label.value,
                "callout_id": callout_id,
            },
        )
        return WriteBackResult(
            status="simulated",
            external_ref=None,
            detail="write-back disabled in settings (ukg_write_back_enabled=False)",
        )

    try:
        token = _fetch_bearer_token(settings)
        payload: dict[str, Any] = {
            "operations": [
                {
                    "op": "replace",
                    "employee_id": employee_id,
                    "unit_id": unit_id,
                    "shift_date": shift_date.isoformat(),
                    "shift_label": shift_label.value,
                    "callout_ref": callout_id,
                }
            ]
        }
        req = urllib.request.Request(
            f"{settings.ukg_base_url.rstrip('/')}/schedule/multi-update",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return WriteBackResult(
            status="applied",
            external_ref=body.get("id"),
            detail="schedule/multi-update succeeded",
        )
    except Exception as exc:  # noqa: BLE001 - boundary with external system
        logger.exception("wfm_writeback_failed")
        return WriteBackResult(status="error", external_ref=None, detail=str(exc))
