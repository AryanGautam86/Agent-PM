from __future__ import annotations

import uuid
from collections.abc import Sequence

from agent_pm.core.enums import EventStatus, EventType
from agent_pm.models.event import AgentEvent
from agent_pm.repositories.base import BaseRepository


class AgentEventRepository(BaseRepository[AgentEvent]):
    model = AgentEvent

    async def find_by_external_id(self, source: str, external_id: str) -> AgentEvent | None:
        """Idempotency for retried deliveries from the Meeting Agent."""
        return await self.find_one(
            AgentEvent.source == source, AgentEvent.external_id == external_id
        )

    async def list_for_engagement(
        self,
        engagement_id: uuid.UUID,
        *,
        event_type: EventType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[AgentEvent]:
        conditions = [AgentEvent.engagement_id == engagement_id]
        if event_type:
            conditions.append(AgentEvent.type == event_type)
        return await self.find_many(
            *conditions, order_by=AgentEvent.created_at.desc(), limit=limit, offset=offset
        )

    async def list_unprocessed(self, *, limit: int = 50) -> Sequence[AgentEvent]:
        return await self.find_many(
            AgentEvent.direction == "inbound",
            AgentEvent.status == EventStatus.RECEIVED,
            order_by=AgentEvent.created_at.asc(),
            limit=limit,
        )
