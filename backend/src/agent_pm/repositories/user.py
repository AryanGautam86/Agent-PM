from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from agent_pm.models.user import EngagementMember, User
from agent_pm.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        return await self.find_one(User.email == email.lower())

    async def list_by_ids(self, ids: Sequence[uuid.UUID]) -> Sequence[User]:
        if not ids:
            return []
        return await self.find_many(User.id.in_(ids))


class EngagementMemberRepository(BaseRepository[EngagementMember]):
    model = EngagementMember

    async def get_membership(
        self, engagement_id: uuid.UUID, user_id: uuid.UUID
    ) -> EngagementMember | None:
        return await self.find_one(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.user_id == user_id,
        )

    async def list_members(self, engagement_id: uuid.UUID) -> Sequence[EngagementMember]:
        """Members with their user rows eagerly loaded.

        Standup generation needs every member's display name at once; without
        the eager load this is one query per person.
        """
        result = await self.session.execute(
            select(EngagementMember)
            .where(EngagementMember.engagement_id == engagement_id)
            .options(joinedload(EngagementMember.user))
            .order_by(EngagementMember.pod_role)
        )
        return result.unique().scalars().all()

    async def list_engagement_ids_for_user(self, user_id: uuid.UUID) -> Sequence[uuid.UUID]:
        result = await self.session.execute(
            select(EngagementMember.engagement_id).where(EngagementMember.user_id == user_id)
        )
        return list(result.scalars().all())
