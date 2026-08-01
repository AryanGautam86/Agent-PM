from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from agent_pm.core.enums import StandupKind
from agent_pm.models.standup import Standup
from agent_pm.repositories.base import EngagementScopedRepository


class StandupRepository(EngagementScopedRepository[Standup]):
    model = Standup

    async def get_for_day(
        self, engagement_id: uuid.UUID, kind: StandupKind, for_date: date
    ) -> Standup | None:
        """The idempotency lookup. Backed by the unique constraint."""
        return await self.find_one(
            Standup.engagement_id == engagement_id,
            Standup.kind == kind,
            Standup.for_date == for_date,
        )

    async def list_recent(
        self,
        engagement_id: uuid.UUID,
        *,
        kind: StandupKind | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> Sequence[Standup]:
        conditions = [Standup.kind == kind] if kind else []
        return await self.list_for_engagement(
            engagement_id,
            *conditions,
            order_by=Standup.for_date.desc(),
            limit=limit,
            offset=offset,
        )

    async def latest(
        self, engagement_id: uuid.UUID, kind: StandupKind, *, before: date | None = None
    ) -> Standup | None:
        """Most recent post of a kind — the morning task's 'prior EOD' input."""
        conditions = [Standup.kind == kind]
        if before is not None:
            conditions.append(Standup.for_date < before)
        results = await self.list_for_engagement(
            engagement_id, *conditions, order_by=Standup.for_date.desc(), limit=1
        )
        return results[0] if results else None
