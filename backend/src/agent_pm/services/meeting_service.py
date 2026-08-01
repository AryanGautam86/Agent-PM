"""Processing of ``meeting_outcome`` events.

Kept separate from :mod:`agent_pm.services.event_service` so intake stays fast:
the webhook stores and acknowledges, and this runs the agent task afterwards.
A slow Anthropic call must never turn into a Meeting Agent retry storm.
"""

from __future__ import annotations

from typing import Any

from dateutil import parser as date_parser
from sqlalchemy.ext.asyncio import AsyncSession

from agent_pm.agents.registry import get_task
from agent_pm.core.enums import ActionItemSource, EventType
from agent_pm.core.errors import AgentPMError
from agent_pm.core.logging import get_logger
from agent_pm.models.event import AgentEvent
from agent_pm.schemas.action_item import ActionItemCreate
from agent_pm.schemas.event import EventIntakeResult
from agent_pm.services.action_item_service import ActionItemService
from agent_pm.services.agent_runner import AgentRunner
from agent_pm.services.engagement_service import EngagementService
from agent_pm.services.event_service import EventService

logger = get_logger(__name__)


def _parse_due(value: Any) -> Any:
    if not value:
        return None
    try:
        return date_parser.parse(str(value))
    except (ValueError, TypeError):
        # A malformed due date becomes no due date rather than a failed
        # meeting: the action item still matters.
        return None


class MeetingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventService(session)
        self.engagements = EngagementService(session)
        self.actions = ActionItemService(session)
        self.runner = AgentRunner(session)

    async def process(self, event: AgentEvent) -> EventIntakeResult:
        """Turn a stored envelope into proposals and action items."""
        self.events.assert_processable(event)
        assert event.engagement_id is not None  # guaranteed by assert_processable

        engagement = await self.engagements.engagements.get_or_raise(event.engagement_id)
        members = await self.engagements.get_members(event.engagement_id)

        try:
            outcome = await self.runner.run(
                get_task("meeting_outcome_intake"),
                engagement,
                members,
                trigger="event",
                prior={"meeting_outcome": event.payload},
            )
        except AgentPMError as exc:
            await self.events.mark_processed(event, error=exc.message)
            raise

        if outcome.skipped:
            await self.events.mark_processed(event)
            return EventIntakeResult(
                event_id=event.id,
                status=event.status,
                message=outcome.result.skip_reason,
            )

        raw_actions = outcome.result.artifact.get("action_items", [])
        created = await self.actions.create_many(
            event.engagement_id,
            [
                ActionItemCreate(
                    title=str(entry.get("title", "")).strip(),
                    owner_label=entry.get("owner_label"),
                    due_at=_parse_due(entry.get("due")),
                    source=ActionItemSource.MEETING_OUTCOME,
                    source_ref=entry.get("source_ref"),
                )
                for entry in raw_actions
                if str(entry.get("title", "")).strip()
            ],
        )

        await self.events.mark_processed(event)
        await self.events.emit(
            EventType.PM_SUMMARY,
            engagement_id=event.engagement_id,
            payload={
                "source_event_id": str(event.id),
                "approvals_created": len(outcome.approvals),
                "action_items_created": len(created),
                "summary_markdown": outcome.result.summary_markdown,
            },
        )

        logger.info(
            "meeting_outcome_processed",
            extra={
                "event_id": str(event.id),
                "approvals": len(outcome.approvals),
                "action_items": len(created),
            },
        )
        return EventIntakeResult(
            event_id=event.id,
            status=event.status,
            approvals_created=len(outcome.approvals),
            action_items_created=len(created),
        )
