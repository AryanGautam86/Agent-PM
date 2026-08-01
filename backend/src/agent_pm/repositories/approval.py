from __future__ import annotations

import uuid
from collections.abc import Sequence

from agent_pm.core.clock import utc_now
from agent_pm.core.enums import ApprovalKind, ApprovalStatus
from agent_pm.models.approval import Approval
from agent_pm.repositories.base import EngagementScopedRepository


class ApprovalRepository(EngagementScopedRepository[Approval]):
    model = Approval

    async def list_pending(self, engagement_id: uuid.UUID) -> Sequence[Approval]:
        return await self.list_for_engagement(
            engagement_id,
            Approval.status == ApprovalStatus.PENDING,
            order_by=Approval.created_at.asc(),
        )

    async def list_all(
        self,
        engagement_id: uuid.UUID,
        *,
        status: ApprovalStatus | None = None,
        kind: ApprovalKind | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Approval]:
        conditions = []
        if status is not None:
            conditions.append(Approval.status == status)
        if kind is not None:
            conditions.append(Approval.kind == kind)
        return await self.list_for_engagement(
            engagement_id,
            *conditions,
            order_by=Approval.created_at.desc(),
            limit=limit,
            offset=offset,
        )

    async def find_pending_duplicate(
        self, engagement_id: uuid.UUID, kind: ApprovalKind, title: str
    ) -> Approval | None:
        """Stops a daily task from re-asking the same question every morning."""
        return await self.find_one(
            Approval.engagement_id == engagement_id,
            Approval.kind == kind,
            Approval.title == title,
            Approval.status == ApprovalStatus.PENDING,
        )

    async def list_expired(self, *, limit: int = 200) -> Sequence[Approval]:
        """Across all engagements — the auto-deny sweep."""
        return await self.find_many(
            Approval.status == ApprovalStatus.PENDING,
            Approval.expires_at.is_not(None),
            Approval.expires_at < utc_now(),
            order_by=Approval.expires_at.asc(),
            limit=limit,
        )

    async def count_by_status(
        self, engagement_id: uuid.UUID, status: ApprovalStatus
    ) -> int:
        return await self.count(
            Approval.engagement_id == engagement_id, Approval.status == status
        )
