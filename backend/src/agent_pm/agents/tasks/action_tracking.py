"""Action-item tracking, nudges and escalation.

Brief: *track every action item; nudge owners 24h before due; escalate overdue
to PO.* L4 for nudges, L3 for escalations.

No model is involved. Deciding who to nudge is arithmetic over due dates and a
fatigue cap, and a model here would add cost, latency and a hallucination
surface to a decision that has one correct answer. The agent framework is still
the right home for it: it inherits the audit row, the autonomy gate and the
scheduler wiring.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel

from agent_pm.agents.base import AgentTask
from agent_pm.agents.context import TaskContext
from agent_pm.agents.results import TaskResult
from agent_pm.core.clock import utc_now
from agent_pm.core.enums import AutonomyLevel
from agent_pm.core.logging import get_logger
from agent_pm.integrations.teams.base import CardSection, ChannelCard

logger = get_logger(__name__)


class ActionItemView(BaseModel):
    """Flat projection of an ``ActionItem``, passed in via ``ctx.prior``."""

    id: str
    title: str
    owner_label: str | None = None
    owner_user_id: str | None = None
    owner_email: str | None = None
    due_at: datetime | None = None
    nudge_count: int = 0
    last_nudged_at: datetime | None = None
    escalated_at: datetime | None = None
    nudges_muted: bool = False


class ActionItemTrackingTask(AgentTask):
    name = "action_item_tracking"
    title = "Action-item tracking"
    description = (
        "Nudge owners before an action item is due and escalate overdue items "
        "to the product owner."
    )

    # The higher of the two levels in the brief. Escalation is the L3 part and
    # is handled by the service, which surfaces it to the PO for review.
    autonomy = AutonomyLevel.L4_AUTONOMOUS
    requires_citations = False  # no external claims are made
    posts_to_channel = True
    auto_execute_writes = True  # a nudge is a message, not a system of record

    async def gather(self, ctx: TaskContext) -> dict[str, Any]:
        """Items come from the service — this task reads no integration."""
        raw = ctx.prior.get("open_items", [])
        items = [
            item if isinstance(item, ActionItemView) else ActionItemView.model_validate(item)
            for item in raw
        ]
        return {
            "items": items,
            "nudges_today": dict(ctx.prior.get("nudges_today", {})),
        }

    async def reason(self, ctx: TaskContext, evidence: dict[str, Any]) -> TaskResult:
        items: list[ActionItemView] = evidence["items"]
        nudges_today: dict[str, int] = evidence["nudges_today"]

        now = utc_now()
        lead = timedelta(hours=float(ctx.param("nudge_lead_time_hours", 24)))
        cap = int(ctx.param("max_nudges_per_person_per_day", 3))

        to_nudge: list[dict[str, Any]] = []
        to_escalate: list[dict[str, Any]] = []
        suppressed: list[str] = []

        for item in items:
            if item.due_at is None or item.nudges_muted:
                continue

            if item.due_at < now:
                if item.escalated_at is None:
                    to_escalate.append(
                        {
                            "id": item.id,
                            "title": item.title,
                            "owner": item.owner_label,
                            "overdue_hours": round(
                                (now - item.due_at).total_seconds() / 3600, 1
                            ),
                        }
                    )
                continue

            if item.due_at - now > lead:
                continue

            # Once per item per day, and never past the per-person cap.
            if item.last_nudged_at and (now - item.last_nudged_at) < timedelta(hours=20):
                continue

            owner_key = item.owner_user_id or item.owner_label or "unknown"
            if nudges_today.get(owner_key, 0) >= cap:
                suppressed.append(item.title)
                continue

            nudges_today[owner_key] = nudges_today.get(owner_key, 0) + 1
            to_nudge.append(
                {
                    "id": item.id,
                    "title": item.title,
                    "owner": item.owner_label,
                    "owner_user_id": item.owner_user_id,
                    "owner_email": item.owner_email,
                    "due_at": item.due_at.isoformat(),
                    "hours_until_due": round(
                        (item.due_at - now).total_seconds() / 3600, 1
                    ),
                }
            )

        if not to_nudge and not to_escalate and not suppressed:
            return TaskResult.skip(self.name, "No action items need attention.")

        # If everything was withheld by the fatigue cap, that is a result worth
        # reporting, not a no-op: an operator needs to see that people are
        # hitting the ceiling, otherwise a silenced reminder looks the same as
        # a reminder that was never due.

        return TaskResult(
            task_name=self.name,
            artifact={
                "nudges": to_nudge,
                "escalations": to_escalate,
                "suppressed_by_cap": suppressed,
            },
            card=self._card(ctx, to_escalate) if to_escalate else None,
            summary_markdown=(
                f"{len(to_nudge)} nudge(s), {len(to_escalate)} escalation(s)"
                + (f", {len(suppressed)} suppressed by the daily cap" if suppressed else "")
            ),
            notes=[f"Nudge cap suppressed: {title}" for title in suppressed],
        )

    @staticmethod
    def _card(ctx: TaskContext, escalations: list[dict[str, Any]]) -> ChannelCard:
        return ChannelCard(
            title=f"Overdue action items — {ctx.engagement.name}",
            subtitle=f"{len(escalations)} item(s) past due",
            accent="attention",
            sections=[
                CardSection(
                    body_markdown="\n".join(
                        f"- **{entry['title']}** — {entry['owner'] or 'unassigned'} "
                        f"_({entry['overdue_hours']:.0f}h overdue)_"
                        for entry in escalations
                    )
                )
            ],
        )
