from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from agent_pm.api.deps import CurrentUserDep, DbSession, EditorUserDep
from agent_pm.schemas.auth import MemberCreate, MemberRead
from agent_pm.schemas.common import Acknowledgement
from agent_pm.schemas.engagement import (
    EngagementCreate,
    EngagementDetail,
    EngagementRead,
    EngagementSummary,
    EngagementUpdate,
)
from agent_pm.services.engagement_service import EngagementService

router = APIRouter(prefix="/engagements", tags=["engagements"])


@router.get("", response_model=list[EngagementRead], summary="List my engagements")
async def list_engagements(
    user: CurrentUserDep, session: DbSession
) -> list[EngagementRead]:
    engagements = await EngagementService(session).list_for_user(user)
    return [EngagementRead.from_model(engagement) for engagement in engagements]


@router.get(
    "/summary",
    response_model=list[EngagementSummary],
    summary="Headline counts for every project",
)
async def list_summaries(
    user: CurrentUserDep, session: DbSession
) -> list[EngagementSummary]:
    """Powers the dashboard. Declared before /{engagement_id} so "summary" is
    not swallowed as a UUID path parameter."""
    return await EngagementService(session).summaries(user)


@router.post(
    "",
    response_model=EngagementRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an engagement",
)
async def create_engagement(
    payload: EngagementCreate, user: EditorUserDep, session: DbSession
) -> EngagementRead:
    engagement = await EngagementService(session).create(payload, user)
    return EngagementRead.from_model(engagement)


@router.get(
    "/{engagement_id}", response_model=EngagementDetail, summary="Engagement detail"
)
async def get_engagement(
    engagement_id: uuid.UUID, user: CurrentUserDep, session: DbSession
) -> EngagementDetail:
    service = EngagementService(session)
    engagement = await service.require_access(engagement_id, user)
    members = await service.get_members(engagement_id)

    detail = EngagementDetail.model_validate(engagement)
    detail.agent_identity = engagement.agent_identity
    detail.members = [MemberRead.model_validate(member) for member in members]
    return detail


@router.patch(
    "/{engagement_id}", response_model=EngagementRead, summary="Update an engagement"
)
async def update_engagement(
    engagement_id: uuid.UUID,
    payload: EngagementUpdate,
    user: EditorUserDep,
    session: DbSession,
) -> EngagementRead:
    engagement = await EngagementService(session).update(engagement_id, payload, user)
    return EngagementRead.from_model(engagement)


@router.delete(
    "/{engagement_id}", response_model=Acknowledgement, summary="Archive a project"
)
async def archive_engagement(
    engagement_id: uuid.UUID, user: EditorUserDep, session: DbSession
) -> Acknowledgement:
    """Hides the project everywhere without deleting it.

    Its standups, RAID items, approvals and agent runs are kept — deleting the
    engagement would cascade through all of them and destroy the record of who
    approved what.
    """
    engagement = await EngagementService(session).archive(engagement_id, user)
    return Acknowledgement(message=f"{engagement.name} archived")


@router.get(
    "/{engagement_id}/members",
    response_model=list[MemberRead],
    summary="List pod members",
)
async def list_members(
    engagement_id: uuid.UUID, user: CurrentUserDep, session: DbSession
) -> list[MemberRead]:
    service = EngagementService(session)
    await service.require_access(engagement_id, user)
    members = await service.get_members(engagement_id)
    return [MemberRead.model_validate(member) for member in members]


@router.post(
    "/{engagement_id}/members",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a pod member",
)
async def add_member(
    engagement_id: uuid.UUID,
    payload: MemberCreate,
    user: EditorUserDep,
    session: DbSession,
) -> MemberRead:
    membership = await EngagementService(session).add_member(engagement_id, payload, user)
    return MemberRead.model_validate(membership)


@router.delete(
    "/{engagement_id}/members/{member_user_id}",
    response_model=Acknowledgement,
    summary="Remove a pod member",
)
async def remove_member(
    engagement_id: uuid.UUID,
    member_user_id: uuid.UUID,
    user: EditorUserDep,
    session: DbSession,
) -> Acknowledgement:
    await EngagementService(session).remove_member(engagement_id, member_user_id, user)
    return Acknowledgement(message="Member removed")
