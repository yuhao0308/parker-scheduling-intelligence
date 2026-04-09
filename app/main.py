from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.exceptions import AppError
from app.routes import admin, callout, health, lookup, overrides, sync

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            structlog.get_level_from_name(settings.log_level)
        ),
    )
    logger.info("starting", version="0.1.0", shadow_mode=settings.shadow_mode)
    yield
    logger.info("shutting_down")


app = FastAPI(
    title="Parker Scheduling Intelligence",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router, tags=["health"])
app.include_router(callout.router)
app.include_router(overrides.router)
app.include_router(sync.router)
app.include_router(admin.router)
app.include_router(lookup.router)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})
