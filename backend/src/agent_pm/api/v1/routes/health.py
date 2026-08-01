"""Liveness and readiness.

``/live`` answers "is the process up" and touches nothing — it is what Render's
health check polls, so a database blip must not cause a restart loop.
``/ready`` answers "can it serve traffic" and does touch the database.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from agent_pm.api.deps import AppSettings, DbSession
from agent_pm.integrations.registry import get_registry
from agent_pm.schemas.common import HealthStatus

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthStatus, summary="Liveness probe")
async def live(settings: AppSettings) -> HealthStatus:
    return HealthStatus(status="ok", environment=settings.environment.value)


@router.get("/ready", response_model=HealthStatus, summary="Readiness probe")
async def ready(settings: AppSettings, session: DbSession) -> HealthStatus:
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:
        database = f"error: {type(exc).__name__}"

    return HealthStatus(
        status="ok" if database == "ok" else "degraded",
        environment=settings.environment.value,
        database=database,
        integrations=get_registry().describe(),
        scheduler="enabled" if settings.scheduler_enabled else "disabled",
    )
