"""RAID log management and gap scanning."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from agent_pm.agents.registry import get_task
from agent_pm.core.clock import utc_now
from agent_pm.core.enums import RaidStatus
from agent_pm.core.logging import get_logger
from agent_pm.models.raid import RaidItem
from agent_pm.repositories.raid import RaidRepository
from agent_pm.schemas.auth import CurrentUser
from agent_pm.schemas.raid import RaidGapScanResponse, RaidItemCreate, RaidItemUpdate
from agent_pm.services.agent_runner import AgentRunner
from agent_pm.services.engagement_service import EngagementService

logger = get_logger(__name__)


class RaidService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.raid = RaidRepository(session)
        self.engagements = EngagementService(session)
        self.runner = AgentRunner(session)

    # ---- reads -----------------------------------------------------------

    async def list_items(
        self,
        engagement_id: uuid.UUID,
        user: CurrentUser,
        *,
        status: RaidStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Sequence[RaidItem]:
        await self.engagements.require_access(engagement_id, user)
        return await self.raid.list_all(
            engagement_id, status=status, limit=limit, offset=offset
        )

    async def get(
        self, engagement_id: uuid.UUID, item_id: uuid.UUID, user: CurrentUser
    ) -> RaidItem:
        await self.engagements.require_access(engagement_id, user)
        return await self.raid.get_for_engagement(engagement_id, item_id)

    # ---- writes ----------------------------------------------------------

    async def create(
        self, engagement_id: uuid.UUID, payload: RaidItemCreate, user: CurrentUser
    ) -> RaidItem:
        """Manual creation by a human. No approval needed — a person adding a
        row to their own RAID log is not the agent writing to a client system."""
        await self.engagements.require_access(engagement_id, user)
        item = RaidItem(engagement_id=engagement_id, **payload.model_dump())
        self.raid.add(item)
        await self.session.flush()
        return item

    async def update(
        self,
        engagement_id: uuid.UUID,
        item_id: uuid.UUID,
        payload: RaidItemUpdate,
        user: CurrentUser,
    ) -> RaidItem:
        item = await self.get(engagement_id, item_id, user)
        changes = payload.model_dump(exclude_unset=True)

        for field_name, value in changes.items():
            setattr(item, field_name, value)

        if changes.get("status") == RaidStatus.CLOSED and item.closed_at is None:
            item.closed_at = utc_now()
        elif changes.get("status") and changes["status"] != RaidStatus.CLOSED:
            item.closed_at = None

        # The workbook is now behind. A later sync job reconciles; flagging it
        # is honest about the fact that the client-visible copy is stale.
        item.synced_at = None
        await self.session.flush()
        return item

    async def delete(
        self, engagement_id: uuid.UUID, item_id: uuid.UUID, user: CurrentUser
    ) -> None:
        item = await self.get(engagement_id, item_id, user)
        await self.raid.remove(item)

    # ---- gap scan --------------------------------------------------------

    async def run_gap_scan(
        self,
        engagement_id: uuid.UUID,
        user: CurrentUser | None = None,
        *,
        trigger: str = "api",
    ) -> RaidGapScanResponse:
        """Compare Jira blockers with the RAID log.

        Produces approvals, never rows. Nothing reaches the workbook until a
        PO decides.
        """
        engagement = (
            await self.engagements.require_access(engagement_id, user)
            if user is not None
            else await self.engagements.engagements.get_or_raise(engagement_id)
        )
        members = await self.engagements.get_members(engagement_id)

        outcome = await self.runner.run(
            get_task("raid_gap_scan"),
            engagement,
            members,
            trigger=trigger,
            prior={"raid_source_refs": sorted(await self.raid.source_refs(engagement_id))},
            triggered_by_user_id=user.id if user else None,
        )

        artifact = outcome.result.artifact
        return RaidGapScanResponse(
            checked_blockers=int(artifact.get("checked", 0)),
            gaps_found=int(artifact.get("gap_count", 0)),
            approvals_created=len(outcome.approvals),
            gap_keys=list(artifact.get("gap_keys", [])),
            summary_markdown=outcome.result.summary_markdown,
        )

    async def run_risk_promotion(
        self,
        engagement_id: uuid.UUID,
        user: CurrentUser | None = None,
        *,
        trigger: str = "api",
    ) -> int:
        """Propose promoting aged blockers to risks. Returns approvals created."""
        engagement = (
            await self.engagements.require_access(engagement_id, user)
            if user is not None
            else await self.engagements.engagements.get_or_raise(engagement_id)
        )
        members = await self.engagements.get_members(engagement_id)

        promoted = {
            item.source_ref
            for item in await self.raid.list_for_engagement(engagement_id)
            if item.source_ref
        }

        outcome = await self.runner.run(
            get_task("blocker_risk_promotion"),
            engagement,
            members,
            trigger=trigger,
            prior={"promoted_refs": sorted(promoted)},
            triggered_by_user_id=user.id if user else None,
        )
        return len(outcome.approvals)
