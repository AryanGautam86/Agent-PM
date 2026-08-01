from __future__ import annotations

import uuid
from collections.abc import Sequence

from agent_pm.core.enums import RunStatus
from agent_pm.models.run import AgentRun
from agent_pm.repositories.base import BaseRepository


class AgentRunRepository(BaseRepository[AgentRun]):
    """Append-only audit. There is deliberately no update or delete helper —
    the runner mutates the row it opened and nothing else touches it."""

    model = AgentRun

    async def list_for_engagement(
        self,
        engagement_id: uuid.UUID,
        *,
        task_name: str | None = None,
        status: RunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[AgentRun]:
        conditions = [AgentRun.engagement_id == engagement_id]
        if task_name:
            conditions.append(AgentRun.task_name == task_name)
        if status:
            conditions.append(AgentRun.status == status)
        return await self.find_many(
            *conditions, order_by=AgentRun.started_at.desc(), limit=limit, offset=offset
        )

    async def last_successful(
        self, engagement_id: uuid.UUID, task_name: str
    ) -> AgentRun | None:
        runs = await self.find_many(
            AgentRun.engagement_id == engagement_id,
            AgentRun.task_name == task_name,
            AgentRun.status == RunStatus.SUCCESS,
            order_by=AgentRun.started_at.desc(),
            limit=1,
        )
        return runs[0] if runs else None
