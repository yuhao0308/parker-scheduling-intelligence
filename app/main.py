from __future__ import annotations

from contextlib import asynccontextmanager

import logging

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import asyncio

from app.config import settings
from app.exceptions import AppError
from app.routes import (
    admin,
    callout,
    confirmation,
    health,
    lookup,
    overrides,
    schedule,
    sync,
    system,
)
from app.services.rationale import warm_ollama

logger = structlog.get_logger()

# structlog 25.x removed get_level_from_name; use stdlib logging levels
_NAME_TO_LEVEL = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
    "NOTSET": logging.NOTSET,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_level = _NAME_TO_LEVEL.get(settings.log_level.upper(), logging.INFO)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
    )
    logger.info("starting", version="0.1.0", shadow_mode=settings.shadow_mode)
    # Preload Ollama model in the background so the first call-out doesn't pay
    # the cold-load cost. Fire-and-forget — warm_ollama never raises.
    warmup_task = asyncio.create_task(warm_ollama(settings))
    yield
    if not warmup_task.done():
        warmup_task.cancel()
    logger.info("shutting_down")


app = FastAPI(
    title="Parker Scheduling Intelligence",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router, tags=["health"])
# lookup.router owns GET /callouts/recent; it must be registered BEFORE
# callout.router so the literal path isn't shadowed by the dynamic
# GET /callouts/{callout_id:int} added below.
app.include_router(lookup.router)
app.include_router(callout.router)
app.include_router(overrides.router)
app.include_router(sync.router)
app.include_router(admin.router)
app.include_router(schedule.router)
app.include_router(confirmation.router)
app.include_router(system.router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})
