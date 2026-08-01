"""v1 router assembly.

Order matters only for documentation grouping; every prefix is distinct.
"""

from __future__ import annotations

from fastapi import APIRouter

from agent_pm.api.v1.routes import (
    action_items,
    agent,
    approvals,
    auth,
    engagements,
    events,
    health,
    raid,
    reports,
    standups,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(engagements.router)
api_router.include_router(standups.router)
api_router.include_router(raid.router)
api_router.include_router(action_items.router)
api_router.include_router(approvals.router)
api_router.include_router(reports.router)
api_router.include_router(agent.router)
api_router.include_router(events.router)

__all__ = ["api_router"]
