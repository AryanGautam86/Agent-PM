from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from agent_pm.api.deps import CurrentUserDep, DbSession, EditorUserDep, PaginationDep
from agent_pm.core.enums import StandupKind
from agent_pm.schemas.agent import StandupCreate, StandupGenerateRequest, StandupRead
from agent_pm.schemas.common import Acknowledgement
from agent_pm.services.standup_service import StandupService

router = APIRouter(prefix="/engagements/{engagement_id}/standups", tags=["standups"])


@router.get("", response_model=list[StandupRead], summary="List standups")
async def list_standups(
    engagement_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSession,
    page: PaginationDep,
    kind: StandupKind | None = Query(default=None),
) -> list[StandupRead]:
    standups = await StandupService(session).list_items(
        engagement_id, user, kind=kind, limit=page.limit, offset=page.offset
    )
    return [StandupRead.model_validate(standup) for standup in standups]


@router.get("/{standup_id}", response_model=StandupRead, summary="Get one standup")
async def get_standup(
    engagement_id: uuid.UUID,
    standup_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSession,
) -> StandupRead:
    standup = await StandupService(session).get(engagement_id, standup_id, user)
    return StandupRead.model_validate(standup)


@router.post(
    "",
    response_model=StandupRead,
    status_code=status.HTTP_201_CREATED,
    summary="Write a standup yourself",
)
async def create_standup(
    engagement_id: uuid.UUID,
    payload: StandupCreate,
    user: CurrentUserDep,
    session: DbSession,
) -> StandupRead:
    """Replaces any generated post for the same day and kind — a person who
    writes the update is the better source than the agent's draft."""
    standup = await StandupService(session).create_manual(engagement_id, payload, user)
    return StandupRead.model_validate(standup)


@router.delete(
    "/{standup_id}", response_model=Acknowledgement, summary="Delete a standup"
)
async def delete_standup(
    engagement_id: uuid.UUID,
    standup_id: uuid.UUID,
    user: EditorUserDep,
    session: DbSession,
) -> Acknowledgement:
    await StandupService(session).delete(engagement_id, standup_id, user)
    return Acknowledgement(message="Standup deleted")


@router.post(
    "/morning", response_model=StandupRead, summary="Generate the morning sprint plan"
)
async def generate_morning(
    engagement_id: uuid.UUID,
    payload: StandupGenerateRequest,
    user: EditorUserDep,
    session: DbSession,
) -> StandupRead:
    """Idempotent for a given date unless ``force_regenerate`` is set."""
    standup, _ = await StandupService(session).generate(
        engagement_id, StandupKind.MORNING, payload, user
    )
    return StandupRead.model_validate(standup)


@router.post(
    "/eod", response_model=StandupRead, summary="Generate the end-of-day summary"
)
async def generate_eod(
    engagement_id: uuid.UUID,
    payload: StandupGenerateRequest,
    user: EditorUserDep,
    session: DbSession,
) -> StandupRead:
    standup, _ = await StandupService(session).generate(
        engagement_id, StandupKind.EOD, payload, user
    )
    return StandupRead.model_validate(standup)
