"""Weekly client status and sprint planning packs."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from agent_pm.agents.registry import get_task
from agent_pm.core.clock import combine_local, local_today, utc_now
from agent_pm.core.enums import (
    ReportKind,
    ReportStatus,
    StandupKind,
)
from agent_pm.core.errors import ConflictError
from agent_pm.core.logging import get_logger
from agent_pm.models.report import Report
from agent_pm.repositories.report import ReportRepository
from agent_pm.repositories.standup import StandupRepository
from agent_pm.schemas.auth import CurrentUser
from agent_pm.schemas.report import ReportGenerateRequest, ReportUpdate
from agent_pm.services.agent_runner import AgentRunner
from agent_pm.services.engagement_service import EngagementService

logger = get_logger(__name__)

TASK_FOR_KIND = {
    ReportKind.WEEKLY_STATUS: "weekly_client_status",
    ReportKind.SPRINT_PLANNING_PACK: "sprint_planning_prep",
}


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reports = ReportRepository(session)
        self.standups = StandupRepository(session)
        self.engagements = EngagementService(session)
        self.runner = AgentRunner(session)

    # ---- reads -----------------------------------------------------------

    async def list_items(
        self,
        engagement_id: uuid.UUID,
        user: CurrentUser,
        *,
        kind: ReportKind | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> Sequence[Report]:
        await self.engagements.require_access(engagement_id, user)
        return await self.reports.list_recent(
            engagement_id, kind=kind, limit=limit, offset=offset
        )

    async def get(
        self, engagement_id: uuid.UUID, report_id: uuid.UUID, user: CurrentUser
    ) -> Report:
        await self.engagements.require_access(engagement_id, user)
        return await self.reports.get_for_engagement(engagement_id, report_id)

    # ---- generation ------------------------------------------------------

    async def generate(
        self,
        engagement_id: uuid.UUID,
        kind: ReportKind,
        request: ReportGenerateRequest,
        user: CurrentUser | None = None,
        *,
        trigger: str = "api",
    ) -> Report:
        engagement = (
            await self.engagements.require_access(engagement_id, user)
            if user is not None
            else await self.engagements.engagements.get_or_raise(engagement_id)
        )
        members = await self.engagements.get_members(engagement_id)

        period_end = request.period_end or local_today(engagement.timezone)
        period_start = period_end - timedelta(days=6)

        existing = await self.reports.get_for_period(engagement_id, kind, period_start)
        if existing is not None and not request.force_regenerate:
            return existing
        if existing is not None and existing.status is ReportStatus.SENT:
            raise ConflictError(
                "This report has already been sent and cannot be regenerated"
            )

        prior_report = await self.reports.previous(engagement_id, kind, period_start)
        standups = await self.standups.list_recent(
            engagement_id, kind=StandupKind.EOD, limit=7
        )

        outcome = await self.runner.run(
            get_task(TASK_FOR_KIND[kind]),
            engagement,
            members,
            trigger=trigger,
            for_date=period_end,
            prior={
                "prior_report": prior_report.content_markdown if prior_report else None,
                "standups": [entry.summary_markdown for entry in standups],
                "period_start_utc": combine_local(
                    period_start,
                    engagement.morning_post_time,
                    engagement.timezone,
                ),
                "now": utc_now(),
            },
            triggered_by_user_id=user.id if user else None,
        )

        artifact = outcome.result.artifact
        report = existing or Report(
            engagement_id=engagement_id,
            kind=kind,
            period_start=period_start,
            period_end=period_end,
            title="",
        )
        report.title = str(artifact.get("title") or f"{engagement.name} — {kind.value}")
        report.content_markdown = str(artifact.get("content_markdown", ""))
        report.sections = dict(artifact.get("sections", {}))
        report.citations = outcome.result.citation_dicts()
        report.model = outcome.result.model
        report.status = ReportStatus.DRAFT

        if existing is None:
            self.reports.add(report)
        await self.session.flush()

        # No separate Approval row is created. These tasks are still L2 — the
        # document is a draft nobody may send until it is approved — but that
        # review happens on the report itself (draft -> approved -> sent)
        # rather than in an approvals queue. Queuing an approval that no
        # surface exposes would leave the report permanently unsendable.
        return report

    # ---- editing ---------------------------------------------------------

    async def update(
        self,
        engagement_id: uuid.UUID,
        report_id: uuid.UUID,
        payload: ReportUpdate,
        user: CurrentUser,
    ) -> Report:
        report = await self.get(engagement_id, report_id, user)
        if report.status is ReportStatus.SENT:
            raise ConflictError("A sent report cannot be edited")

        for field_name, value in payload.model_dump(exclude_unset=True).items():
            setattr(report, field_name, value)
        await self.session.flush()
        return report

    async def mark_sent(
        self, engagement_id: uuid.UUID, report_id: uuid.UUID, user: CurrentUser
    ) -> Report:
        report = await self.get(engagement_id, report_id, user)
        if report.status is not ReportStatus.APPROVED:
            raise ConflictError(
                "Only an approved report can be marked as sent",
                details={"status": report.status.value},
            )
        report.status = ReportStatus.SENT
        report.sent_at = utc_now()
        await self.session.flush()
        return report

    @staticmethod
    def period_for(today: date) -> tuple[date, date]:
        return today - timedelta(days=6), today
