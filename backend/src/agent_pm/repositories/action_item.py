from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import or_, select

from agent_pm.core.clock import utc_now
from agent_pm.core.enums import ActionItemStatus
from agent_pm.models.action_item import ActionItem
from agent_pm.repositories.base import EngagementScopedRepository

OPEN_STATUSES = (ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS)


class ActionItemRepository(EngagementScopedRepository[ActionItem]):
    model = ActionItem

    async def list_open(self, engagement_id: uuid.UUID) -> Sequence[ActionItem]:
        return await self.list_for_engagement(
            engagement_id,
            ActionItem.status.in_(OPEN_STATUSES),
            order_by=ActionItem.due_at.asc().nullslast(),
        )

    async def list_all(
        self,
        engagement_id: uuid.UUID,
        *,
        status: ActionItemStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Sequence[ActionItem]:
        conditions = [ActionItem.status == status] if status else []
        return await self.list_for_engagement(
            engagement_id,
            *conditions,
            order_by=ActionItem.created_at.desc(),
            limit=limit,
            offset=offset,
        )

    async def due_within(
        self, engagement_id: uuid.UUID, *, before: datetime
    ) -> Sequence[ActionItem]:
        """Open items falling due before a cut-off — the nudge candidates."""
        return await self.list_for_engagement(
            engagement_id,
            ActionItem.status.in_(OPEN_STATUSES),
            ActionItem.due_at.is_not(None),
            ActionItem.due_at <= before,
            ActionItem.nudges_muted.is_(False),
            order_by=ActionItem.due_at.asc(),
        )

    async def overdue(self, engagement_id: uuid.UUID) -> Sequence[ActionItem]:
        return await self.due_within(engagement_id, before=utc_now())

    async def needing_escalation(self, engagement_id: uuid.UUID) -> Sequence[ActionItem]:
        """Overdue and not yet escalated — escalate once, not every hour."""
        return await self.list_for_engagement(
            engagement_id,
            ActionItem.status.in_(OPEN_STATUSES),
            ActionItem.due_at.is_not(None),
            ActionItem.due_at < utc_now(),
            ActionItem.escalated_at.is_(None),
            order_by=ActionItem.due_at.asc(),
        )

    async def nudges_sent_today(self, owner_user_id: uuid.UUID, since: datetime) -> int:
        """Fatigue cap: how many nudges this person has already had today."""
        stmt = select(ActionItem).where(
            ActionItem.owner_user_id == owner_user_id,
            ActionItem.last_nudged_at.is_not(None),
            ActionItem.last_nudged_at >= since,
        )
        result = await self.session.execute(stmt)
        return len(result.scalars().all())

    async def find_duplicate(
        self, engagement_id: uuid.UUID, *, title: str, source_ref: str | None
    ) -> ActionItem | None:
        """Guard against the same meeting action landing twice."""
        return await self.find_one(
            ActionItem.engagement_id == engagement_id,
            ActionItem.status.in_(OPEN_STATUSES),
            or_(
                ActionItem.source_ref == source_ref if source_ref else ActionItem.id.is_(None),
                ActionItem.title == title,
            ),
        )
