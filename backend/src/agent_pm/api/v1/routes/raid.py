from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from agent_pm.api.deps import CurrentUserDep, DbSession, PaginationDep
from agent_pm.core.enums import RaidStatus
from agent_pm.schemas.common import Acknowledgement
from agent_pm.schemas.raid import (
    RaidGapScanResponse,
    RaidItemCreate,
    RaidItemRead,
    RaidItemUpdate,
)
from agent_pm.services.raid_service import RaidService

router = APIRouter(prefix="/engagements/{engagement_id}/raid", tags=["raid"])


@router.get("", response_model=list[RaidItemRead], summary="List RAID items")
async def list_raid(
    engagement_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSession,
    page: PaginationDep,
    raid_status: RaidStatus | None = Query(default=None, alias="status"),
) -> list[RaidItemRead]:
    items = await RaidService(session).list_items(
        engagement_id, user, status=raid_status, limit=page.limit, offset=page.offset
    )
    return [RaidItemRead.model_validate(item) for item in items]


@router.post(
    "",
    response_model=RaidItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a RAID item",
)
async def create_raid(
    engagement_id: uuid.UUID,
    payload: RaidItemCreate,
    user: CurrentUserDep,
    session: DbSession,
) -> RaidItemRead:
    item = await RaidService(session).create(engagement_id, payload, user)
    return RaidItemRead.model_validate(item)


@router.patch("/{item_id}", response_model=RaidItemRead, summary="Update a RAID item")
async def update_raid(
    engagement_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: RaidItemUpdate,
    user: CurrentUserDep,
    session: DbSession,
) -> RaidItemRead:
    item = await RaidService(session).update(engagement_id, item_id, payload, user)
    return RaidItemRead.model_validate(item)


@router.delete(
    "/{item_id}", response_model=Acknowledgement, summary="Delete a RAID item"
)
async def delete_raid(
    engagement_id: uuid.UUID,
    item_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSession,
) -> Acknowledgement:
    await RaidService(session).delete(engagement_id, item_id, user)
    return Acknowledgement(message="RAID item deleted")


@router.post(
    "/gap-scan",
    response_model=RaidGapScanResponse,
    summary="Scan Jira blockers against the RAID log",
)
async def gap_scan(
    engagement_id: uuid.UUID, user: CurrentUserDep, session: DbSession
) -> RaidGapScanResponse:
    """Produces approvals, not rows. Nothing is written until a PO decides."""
    return await RaidService(session).run_gap_scan(engagement_id, user)


@router.post(
    "/risk-promotion",
    response_model=Acknowledgement,
    summary="Propose promoting aged blockers to risks",
)
async def risk_promotion(
    engagement_id: uuid.UUID, user: CurrentUserDep, session: DbSession
) -> Acknowledgement:
    created = await RaidService(session).run_risk_promotion(engagement_id, user)
    return Acknowledgement(message=f"{created} promotion(s) awaiting approval")
