"""FastAPI application factory.

Entry point for Render:

    uvicorn agent_pm.main:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_pm.api.error_handlers import register_error_handlers
from agent_pm.api.middleware import register_middleware
from agent_pm.api.v1.router import api_router
from agent_pm.core.config import Settings, get_settings
from agent_pm.core.logging import configure_logging, get_logger
from agent_pm.db.session import dispose_engine
from agent_pm.integrations.registry import dispose_registry, get_registry

logger = get_logger(__name__)

DESCRIPTION = """\
Delivery Steward — a project management agent for services pods.

Twice-daily standups, RAID log stewardship, action-item tracking, and
human-approved writes to Jira and the RAID log.

**Authentication.** Every endpoint except the health probes and the
meeting-outcome webhook needs `Authorization: Bearer <supabase-access-token>`.
Sign in through Supabase (Google OAuth or email OTP) and send the access token.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)

    registry = get_registry()
    logger.info(
        "application_starting",
        extra={
            "environment": settings.environment.value,
            "integrations": registry.describe(),
            "scheduler_enabled": settings.scheduler_enabled,
        },
    )

    scheduler = None
    if settings.scheduler_enabled:
        # Imported lazily: the API image should not pay for APScheduler when
        # the scheduler runs as a separate Render worker.
        from agent_pm.scheduler.runner import build_scheduler

        scheduler = build_scheduler(settings)
        scheduler.start()
        logger.info("scheduler_started_in_process")

    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        await dispose_registry()
        await dispose_engine()
        logger.info("application_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="Agent-PM — Delivery Steward",
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    register_middleware(app)
    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": "agent-pm",
            "version": "0.1.0",
            "health": f"{settings.api_v1_prefix}/health/ready",
        }

    return app


app = create_app()
