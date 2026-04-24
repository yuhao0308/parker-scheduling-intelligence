from __future__ import annotations

import asyncio
import time

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings

logger = structlog.get_logger()

router = APIRouter()

# Keep the Ollama reachability probe cheap: /api/tags is a metadata call,
# it does not load any model. 5s is generous for that and well under the
# generation timeout in app/config.py.
OLLAMA_HEALTH_TIMEOUT_SECONDS = 5.0


@router.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "version": "0.1.0"}


def _extract_model_names(list_response: object) -> list[str]:
    """Pull model names out of ollama.ListResponse, tolerating shape drift."""
    models = getattr(list_response, "models", None)
    if models is None and isinstance(list_response, dict):
        models = list_response.get("models", [])
    if not models:
        return []
    names: list[str] = []
    for m in models:
        name = getattr(m, "model", None) or getattr(m, "name", None)
        if name is None and isinstance(m, dict):
            name = m.get("model") or m.get("name")
        if name:
            names.append(str(name))
    return names


@router.get("/health/ollama")
async def ollama_health() -> JSONResponse:
    """Probe the configured Ollama host.

    Cheap reachability check: calls /api/tags via the ollama client. Returns
    200 with model names + latency on success, 503 on any failure (timeout,
    connection refused, 403 from Host-header mismatch, etc.). The main
    /health probe is intentionally not coupled to this so Railway's app
    healthcheck stays green independent of Ollama reachability.
    """
    from ollama import AsyncClient

    base_url = settings.ollama_base_url
    client = AsyncClient(host=base_url)
    start = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            client.list(), timeout=OLLAMA_HEALTH_TIMEOUT_SECONDS
        )
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        models = _extract_model_names(response)
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "base_url": base_url,
                "latency_ms": latency_ms,
                "model_count": len(models),
                "models": models,
                "configured_model": settings.ollama_model,
                "configured_model_available": settings.ollama_model in models,
            },
        )
    except Exception as e:
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.warning(
            "ollama_health_probe_failed",
            base_url=base_url,
            error=repr(e),
            error_type=type(e).__name__,
        )
        return JSONResponse(
            status_code=503,
            content={
                "status": "unreachable",
                "base_url": base_url,
                "latency_ms": latency_ms,
                "error_type": type(e).__name__,
                "error": str(e)[:500],
            },
        )
