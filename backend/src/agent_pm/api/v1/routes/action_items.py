from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from agent_pm.api.deps import CurrentUserDep, DbSession, PaginationDep
from agent_pm.core.enums import ActionItemStatus
from agent_pm.schemas.action_item import (
    ActionItemCreate,
    ActionItemRead,
    ActionItemUpdate,
    NudgeSweepResponse,
)
from agent_pm.schemas.common import Acknowledgement
from agent_pm.services.action_item_service import ActionItemService
from agent_pm.services.engagement_service import EngagementService

router = APIRouter(
    prefix="/engagements/{engagement_id}/action-items", tags=["action-items"]
)


@router.get("", response_model=list[ActionItemRead], summary="List action items")
async def list_action_items(
    engagement_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSession,
    page: PaginationDep,
    item_status: ActionItemStatus | None = Query(default=None, alias="status"),
) -> list[ActionItemRead]:
    return await ActionItemService(session).list_items(
        engagement_id, user, status=item_status, limit=page.limit, offset=page.offset
    )


@router.post(
    "",
    response_model=ActionItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an action item",
)
async def create_action_item(
    engagement_id: uuid.UUID,
    payload: ActionItemCreate,
    user: CurrentUserDep,
    session: DbSession,
) -> ActionItemRead:
    service = ActionItemService(session)
    item = await service.create(engagement_id, payload, user)
    return service.to_read(item)


@router.patch(
    "/{item_id}", response_model=ActionItemRead, summary="Update an action item"
)
async def update_action_item(
    engagement_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ActionItemUpdate,
    user: CurrentUserDep,
    session: DbSession,
) -> ActionItemRead:
    service = ActionItemService(session)
    item = await service.update(engagement_id, item_id, payload, user)
    return service.to_read(item)


@router.delete(
    "/{item_id}", response_model=Acknowledgement, summary="Delete a task"
)
async def delete_action_item(
    engagement_id: uuid.UUID,
    item_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSession,
) -> Acknowledgement:
    """Removes it permanently. To keep a record that the work existed but was
    dropped, set the status to ``cancelled`` instead."""
    await ActionItemService(session).delete(engagement_id, item_id, user)
    return Acknowledgement(message="Task deleted")


@router.post(
    "/nudge-sweep",
    response_model=NudgeSweepResponse,
    summary="Run the nudge and escalation sweep now",
)
async def nudge_sweep(
    engagement_id: uuid.UUID, user: CurrentUserDep, session: DbSession
) -> NudgeSweepResponse:
    """Normally scheduled hourly; exposed for testing the cadence manually."""
    await EngagementService(session).require_access(engagement_id, user)
    return await ActionItemService(session).run_nudge_sweep(
        engagement_id, trigger="api"
    )
