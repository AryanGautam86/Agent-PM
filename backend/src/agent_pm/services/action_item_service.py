"""Action items: tracking, nudges and escalation."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from agent_pm.agents.registry import get_task
from agent_pm.agents.tasks.action_tracking import ActionItemView
from agent_pm.core.clock import utc_now
from agent_pm.core.config import get_settings
from agent_pm.core.enums import ActionItemStatus
from agent_pm.core.errors import AgentPMError
from agent_pm.core.logging import get_logger
from agent_pm.integrations.registry import get_registry
from agent_pm.models.action_item import ActionItem
from agent_pm.repositories.action_item import ActionItemRepository
from agent_pm.schemas.action_item import (
    ActionItemCreate,
    ActionItemRead,
    ActionItemUpdate,
    NudgeSweepResponse,
)
from agent_pm.schemas.auth import CurrentUser
from agent_pm.services.agent_runner import AgentRunner
from agent_pm.services.engagement_service import EngagementService

logger = get_logger(__name__)


class ActionItemService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = get_settings()
        self.items = ActionItemRepository(session)
        self.engagements = EngagementService(session)
        self.runner = AgentRunner(session)
        self.registry = get_registry()

    # ---- reads -----------------------------------------------------------

    async def list_items(
        self,
        engagement_id: uuid.UUID,
        user: CurrentUser,
        *,
        status: ActionItemStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ActionItemRead]:
        await self.engagements.require_access(engagement_id, user)
        rows = await self.items.list_all(
            engagement_id, status=status, limit=limit, offset=offset
        )
        return [self.to_read(row) for row in rows]

    @staticmethod
    def to_read(item: ActionItem) -> ActionItemRead:
        read = ActionItemRead.model_validate(item)
        read.is_overdue = item.is_overdue
        return read

    # ---- writes ----------------------------------------------------------

    async def create(
        self, engagement_id: uuid.UUID, payload: ActionItemCreate, user: CurrentUser
    ) -> ActionItem:
        await self.engagements.require_access(engagement_id, user)
        item = ActionItem(engagement_id=engagement_id, **payload.model_dump())
        self.items.add(item)
        await self.session.flush()
        return item

    async def create_many(
        self, engagement_id: uuid.UUID, payloads: Sequence[ActionItemCreate]
    ) -> list[ActionItem]:
        """Bulk path used by meeting intake. Skips duplicates rather than
        raising: a re-delivered meeting must not double the pod's workload."""
        created: list[ActionItem] = []
        for payload in payloads:
            duplicate = await self.items.find_duplicate(
                engagement_id, title=payload.title, source_ref=payload.source_ref
            )
            if duplicate is not None:
                continue
            item = ActionItem(engagement_id=engagement_id, **payload.model_dump())
            self.items.add(item)
            created.append(item)
        if created:
            await self.session.flush()
        return created

    async def update(
        self,
        engagement_id: uuid.UUID,
        item_id: uuid.UUID,
        payload: ActionItemUpdate,
        user: CurrentUser,
    ) -> ActionItem:
        await self.engagements.require_access(engagement_id, user)
        item = await self.items.get_for_engagement(engagement_id, item_id)

        changes = payload.model_dump(exclude_unset=True)
        for field_name, value in changes.items():
            setattr(item, field_name, value)

        if changes.get("status") is ActionItemStatus.DONE and item.completed_at is None:
            item.completed_at = utc_now()
        elif changes.get("status") and changes["status"] is not ActionItemStatus.DONE:
            item.completed_at = None

        await self.session.flush()
        return item

    async def delete(
        self, engagement_id: uuid.UUID, item_id: uuid.UUID, user: CurrentUser
    ) -> None:
        """Remove a task outright.

        A hard delete is right here: unlike an approval or an agent run, a task
        is not an audit record. Something added by mistake should leave no
        trace, and "cancelled" already exists for work that was real but
        dropped.
        """
        await self.engagements.require_access(engagement_id, user)
        item = await self.items.get_for_engagement(engagement_id, item_id)
        await self.items.remove(item)
        logger.info("action_item_deleted", extra={"item_id": str(item_id)})

    # ---- nudge sweep -----------------------------------------------------

    async def run_nudge_sweep(
        self, engagement_id: uuid.UUID, *, trigger: str = "schedule"
    ) -> NudgeSweepResponse:
        """Decide who to nudge and who to escalate, then deliver.

        The agent task decides; this method delivers. Splitting it that way
        keeps the fatigue-cap arithmetic unit-testable without a channel.
        """
        engagement = await self.engagements.engagements.get_or_raise(engagement_id)
        members = await self.engagements.get_members(engagement_id)
        open_items = await self.items.list_open(engagement_id)

        if not open_items:
            return NudgeSweepResponse(nudged=0, escalated=0, suppressed_by_cap=0)

        by_email = {
            member.user.email: member
            for member in members
            if member.user and member.nudges_enabled
        }
        since = utc_now() - timedelta(hours=24)
        nudges_today: dict[str, int] = {}
        for item in open_items:
            if item.owner_user_id and item.last_nudged_at and item.last_nudged_at >= since:
                key = str(item.owner_user_id)
                nudges_today[key] = nudges_today.get(key, 0) + 1

        views = [
            ActionItemView(
                id=str(item.id),
                title=item.title,
                owner_label=item.owner_label,
                owner_user_id=str(item.owner_user_id) if item.owner_user_id else None,
                owner_email=next(
                    (
                        member.user.email
                        for member in members
                        if member.user_id == item.owner_user_id and member.user
                    ),
                    None,
                ),
                due_at=item.due_at,
                nudge_count=item.nudge_count,
                last_nudged_at=item.last_nudged_at,
                escalated_at=item.escalated_at,
                nudges_muted=item.nudges_muted,
            )
            for item in open_items
        ]

        outcome = await self.runner.run(
            get_task("action_item_tracking"),
            engagement,
            members,
            trigger=trigger,
            prior={"open_items": views, "nudges_today": nudges_today},
            params={
                "nudge_lead_time_hours": self.settings.nudge_lead_time_hours,
                "max_nudges_per_person_per_day": self.settings.max_nudges_per_person_per_day,
            },
        )

        if outcome.skipped:
            return NudgeSweepResponse(nudged=0, escalated=0, suppressed_by_cap=0)

        artifact = outcome.result.artifact
        by_id = {str(item.id): item for item in open_items}
        detail: list[str] = []

        delivered = 0
        for entry in artifact.get("nudges", []):
            target = by_id.get(str(entry.get("id")))
            if target is None:
                continue
            recipient = entry.get("owner_email")
            if not recipient or recipient not in by_email:
                detail.append(f"No channel identity for {entry.get('owner')}")
                continue
            try:
                await self.registry.channel.send_direct_message(
                    recipient,
                    f"Reminder: **{target.title}** is due in "
                    f"{entry.get('hours_until_due')}h.",
                )
            except AgentPMError as exc:
                # Count only nudges that were actually delivered — an
                # undelivered one must stay eligible for the next sweep.
                detail.append(f"Nudge failed for {recipient}: {exc.message}")
                continue

            target.nudge_count += 1
            target.last_nudged_at = utc_now()
            delivered += 1

        escalated = 0
        for entry in artifact.get("escalations", []):
            target = by_id.get(str(entry.get("id")))
            if target is None:
                continue
            target.escalated_at = utc_now()
            escalated += 1

        await self.session.flush()
        return NudgeSweepResponse(
            nudged=delivered,
            escalated=escalated,
            suppressed_by_cap=len(artifact.get("suppressed_by_cap", [])),
            detail=detail + outcome.result.notes,
        )
