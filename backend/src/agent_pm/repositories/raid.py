from __future__ import annotations

import uuid
from collections.abc import Sequence

from agent_pm.core.enums import RaidStatus, RaidType
from agent_pm.models.raid import RaidItem
from agent_pm.repositories.base import EngagementScopedRepository


class RaidRepository(EngagementScopedRepository[RaidItem]):
    model = RaidItem

    async def list_open(
        self, engagement_id: uuid.UUID, *, raid_type: RaidType | None = None
    ) -> Sequence[RaidItem]:
        conditions = [RaidItem.status != RaidStatus.CLOSED]
        if raid_type is not None:
            conditions.append(RaidItem.type == raid_type)
        return await self.list_for_engagement(
            engagement_id, *conditions, order_by=RaidItem.severity.desc()
        )

    async def list_all(
        self,
        engagement_id: uuid.UUID,
        *,
        status: RaidStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Sequence[RaidItem]:
        conditions = [RaidItem.status == status] if status else []
        return await self.list_for_engagement(
            engagement_id,
            *conditions,
            order_by=RaidItem.created_at.desc(),
            limit=limit,
            offset=offset,
        )

    async def source_refs(self, engagement_id: uuid.UUID) -> set[str]:
        """Every external reference already represented in the RAID log.

        The gap scan compares Jira blocker keys against this set; anything not
        in it is a candidate gap. Returned as a set so the scan is O(1) per
        blocker rather than a query per blocker.
        """
        items = await self.list_for_engagement(engagement_id)
        return {item.source_ref for item in items if item.source_ref}

    async def find_by_source_ref(
        self, engagement_id: uuid.UUID, source_ref: str
    ) -> RaidItem | None:
        return await self.find_one(
            RaidItem.engagement_id == engagement_id,
            RaidItem.source_ref == source_ref,
        )
