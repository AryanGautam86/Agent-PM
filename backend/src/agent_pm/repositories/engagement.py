from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select

from agent_pm.models.engagement import Engagement
from agent_pm.models.user import EngagementMember
from agent_pm.repositories.base import BaseRepository


class EngagementRepository(BaseRepository[Engagement]):
    model = Engagement

    async def get_by_slug(self, slug: str) -> Engagement | None:
        return await self.find_one(Engagement.slug == slug)

    async def list_active(self) -> Sequence[Engagement]:
        """Every active engagement — the scheduler's work list."""
        return await self.find_many(
            Engagement.is_active.is_(True), order_by=Engagement.name
        )

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[Engagement]:
        result = await self.session.execute(
            select(Engagement)
            .join(EngagementMember, EngagementMember.engagement_id == Engagement.id)
            .where(EngagementMember.user_id == user_id, Engagement.is_active.is_(True))
            .order_by(Engagement.name)
        )
        return result.scalars().all()

    async def slug_taken(self, slug: str) -> bool:
        return await self.exists(Engagement.slug == slug)
