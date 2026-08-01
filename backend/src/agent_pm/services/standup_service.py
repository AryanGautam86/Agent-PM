"""Standup generation — the daily morning and EOD posts."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from agent_pm.agents.registry import get_task
from agent_pm.core.clock import local_today, previous_working_day, utc_now
from agent_pm.core.enums import EventType, StandupKind, StandupStatus
from agent_pm.core.logging import get_logger
from agent_pm.models.engagement import Engagement
from agent_pm.models.standup import Standup
from agent_pm.repositories.standup import StandupRepository
from agent_pm.schemas.agent import StandupCreate, StandupGenerateRequest
from agent_pm.schemas.auth import CurrentUser
from agent_pm.services.agent_runner import AgentRunner, RunOutcome
from agent_pm.services.engagement_service import EngagementService
from agent_pm.services.event_service import EventService

logger = get_logger(__name__)

TASK_FOR_KIND = {
    StandupKind.MORNING: "morning_sprint_plan",
    StandupKind.EOD: "eod_summary",
}


class StandupService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.standups = StandupRepository(session)
        self.engagements = EngagementService(session)
        self.runner = AgentRunner(session)
        self.events = EventService(session)

    # ---- reads -----------------------------------------------------------

    async def list_items(
        self,
        engagement_id: uuid.UUID,
        user: CurrentUser,
        *,
        kind: StandupKind | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> Sequence[Standup]:
        await self.engagements.require_access(engagement_id, user)
        return await self.standups.list_recent(
            engagement_id, kind=kind, limit=limit, offset=offset
        )

    async def get(
        self, engagement_id: uuid.UUID, standup_id: uuid.UUID, user: CurrentUser
    ) -> Standup:
        await self.engagements.require_access(engagement_id, user)
        return await self.standups.get_for_engagement(engagement_id, standup_id)

    # ---- manual entry ----------------------------------------------------

    async def create_manual(
        self,
        engagement_id: uuid.UUID,
        payload: StandupCreate,
        user: CurrentUser,
    ) -> Standup:
        """Record a standup somebody wrote themselves.

        Overwrites a generated post for the same day on purpose: a human who
        takes the trouble to write the update is the better source, and the
        unique constraint on (engagement, kind, date) means there is one
        standup per slot by design.

        It is stored with no citations and no grounding ratio — those describe
        how well the *agent* evidenced a claim, and asserting them for text a
        person typed would be a lie in the audit trail.
        """
        engagement = await self.engagements.require_access(engagement_id, user)
        for_date = payload.for_date or local_today(engagement.timezone)

        standup = await self.standups.get_for_day(engagement_id, payload.kind, for_date)
        if standup is None:
            standup = Standup(
                engagement_id=engagement_id, kind=payload.kind, for_date=for_date
            )
            self.standups.add(standup)

        standup.topic = payload.topic.strip()
        standup.summary_markdown = payload.summary_markdown.strip()
        standup.author_user_id = user.id
        standup.status = StandupStatus.POSTED
        standup.posted_at = utc_now()
        standup.generated_at = utc_now()
        standup.model = None
        standup.grounding_ratio = None
        standup.citations = []
        standup.error = None

        await self.session.flush()
        logger.info(
            "standup_written_manually",
            extra={"engagement": engagement.slug, "kind": payload.kind.value},
        )
        return standup

    async def delete(
        self, engagement_id: uuid.UUID, standup_id: uuid.UUID, user: CurrentUser
    ) -> None:
        await self.engagements.require_access(engagement_id, user)
        standup = await self.standups.get_for_engagement(engagement_id, standup_id)
        await self.standups.remove(standup)

    # ---- generation ------------------------------------------------------

    async def generate(
        self,
        engagement_id: uuid.UUID,
        kind: StandupKind,
        request: StandupGenerateRequest,
        user: CurrentUser | None = None,
        *,
        trigger: str = "api",
    ) -> tuple[Standup, RunOutcome | None]:
        engagement = (
            await self.engagements.require_access(engagement_id, user)
            if user is not None
            else await self._load_engagement(engagement_id)
        )
        for_date = request.for_date or local_today(engagement.timezone)

        existing = await self.standups.get_for_day(engagement_id, kind, for_date)
        if existing is not None and not request.force_regenerate:
            # Idempotent by default: a scheduler retry or a double-click must
            # not produce a second post for the same morning.
            logger.info(
                "standup_already_exists",
                extra={"engagement": engagement.slug, "kind": kind.value},
            )
            return existing, None

        members = await self.engagements.get_members(engagement_id)
        task = get_task(TASK_FOR_KIND[kind])
        prior = await self._build_prior(engagement_id, kind, for_date)

        outcome = await self.runner.run(
            task,
            engagement,
            members,
            trigger=trigger,
            for_date=for_date,
            prior=prior,
            params={"post_to_channel": request.post_to_channel},
            triggered_by_user_id=user.id if user else None,
        )

        standup = existing or Standup(
            engagement_id=engagement_id, kind=kind, for_date=for_date
        )

        if outcome.skipped:
            standup.status = StandupStatus.FAILED
            standup.error = outcome.result.skip_reason
            standup.summary_markdown = outcome.result.skip_reason or ""
        else:
            self._apply_result(standup, outcome)

        if existing is None:
            self.standups.add(standup)
        await self.session.flush()

        if kind is StandupKind.EOD and not outcome.skipped:
            # The brief's downstream contract: EOD emits an event other agents
            # can subscribe to.
            await self.events.emit(
                EventType.PM_EOD_SUMMARY,
                engagement_id=engagement_id,
                payload={
                    "for_date": for_date.isoformat(),
                    "summary_markdown": standup.summary_markdown,
                    "metrics": standup.metrics,
                    "blockers": standup.blockers,
                },
            )

        return standup, outcome

    async def _build_prior(
        self, engagement_id: uuid.UUID, kind: StandupKind, for_date: date
    ) -> dict[str, object]:
        """Context the task cannot fetch for itself, because it has no database."""
        if kind is StandupKind.MORNING:
            prior_eod = await self.standups.latest(
                engagement_id, StandupKind.EOD, before=for_date
            ) or await self.standups.get_for_day(
                engagement_id, StandupKind.EOD, previous_working_day(for_date)
            )
            return {"prior_eod": prior_eod.summary_markdown if prior_eod else None}

        morning = await self.standups.get_for_day(
            engagement_id, StandupKind.MORNING, for_date
        )
        return {
            "morning_post": morning.summary_markdown if morning else None,
            "since": morning.generated_at if morning else None,
        }

    @staticmethod
    def _apply_result(standup: Standup, outcome: RunOutcome) -> None:
        result = outcome.result
        artifact = result.artifact

        standup.summary_markdown = result.summary_markdown
        standup.per_person = artifact.get("per_person", [])
        standup.blockers = artifact.get("blockers", [])
        standup.highlights = artifact.get("highlights", [])
        standup.metrics = artifact.get("metrics", {})
        standup.citations = result.citation_dicts()
        standup.model = result.model
        standup.grounding_ratio = result.grounding_ratio
        standup.generated_at = utc_now()
        standup.error = None

        if outcome.posted:
            standup.status = StandupStatus.POSTED
            standup.posted_at = utc_now()
        else:
            standup.status = StandupStatus.DRAFT

    async def _load_engagement(self, engagement_id: uuid.UUID) -> Engagement:
        """Scheduler path — no user, so no membership check."""
        engagement = await self.engagements.engagements.get_or_raise(engagement_id)
        return engagement
