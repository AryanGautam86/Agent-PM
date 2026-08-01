from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from agent_pm.core.enums import ReportKind
from agent_pm.models.report import Report
from agent_pm.repositories.base import EngagementScopedRepository


class ReportRepository(EngagementScopedRepository[Report]):
    model = Report

    async def get_for_period(
        self, engagement_id: uuid.UUID, kind: ReportKind, period_start: date
    ) -> Report | None:
        return await self.find_one(
            Report.engagement_id == engagement_id,
            Report.kind == kind,
            Report.period_start == period_start,
        )

    async def list_recent(
        self,
        engagement_id: uuid.UUID,
        *,
        kind: ReportKind | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> Sequence[Report]:
        conditions = [Report.kind == kind] if kind else []
        return await self.list_for_engagement(
            engagement_id,
            *conditions,
            order_by=Report.period_start.desc(),
            limit=limit,
            offset=offset,
        )

    async def previous(
        self, engagement_id: uuid.UUID, kind: ReportKind, before: date
    ) -> Report | None:
        """Last week's report — context for continuity in the narrative."""
        results = await self.list_for_engagement(
            engagement_id,
            Report.kind == kind,
            Report.period_start < before,
            order_by=Report.period_start.desc(),
            limit=1,
        )
        return results[0] if results else None
