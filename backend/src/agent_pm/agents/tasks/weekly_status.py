"""Weekly client status.

Brief: *aggregate sprint progress, velocity, scope delta, risks, decisions.*
Autonomy L2 — the Engagement Lead reviews and sends. This is the one task the
brief routes to the stronger model, because it is the only output a client
reads directly.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from agent_pm.agents.base import AgentTask
from agent_pm.agents.context import TaskContext
from agent_pm.agents.prompts import narrative_schema
from agent_pm.agents.results import TaskResult
from agent_pm.core.clock import utc_now
from agent_pm.core.enums import ApprovalKind, AutonomyLevel, ModelTier
from agent_pm.core.logging import get_logger

logger = get_logger(__name__)

INSTRUCTIONS = """\
Write this week's client status report. The reader is a client stakeholder who
was not in any of the delivery conversations.

Sections, in this order:
1. **Where we are** — two or three sentences. Progress against the sprint goal,
   stated plainly. If we are behind, say so in the first sentence.
2. **Delivered this week** — what completed, in outcome terms. "Users can now
   reset a password by SMS", not "closed DEMO-104".
3. **In progress** — what is underway and when it lands.
4. **Risks and issues** — what could go wrong, what we are doing about it, and
   what we need from the client. Never soften a risk to make the report read
   better.
5. **Decisions and changes** — scope changes and decisions taken, with who took
   them.

No internal jargon, no ticket keys in the prose. The evidence carries the
keys; the report carries the meaning. Aim for 300–400 words.
"""

STATUS_SCHEMA = narrative_schema(
    {
        "headline": {
            "type": "string",
            "description": "One sentence a client could forward on its own.",
        },
        "status_rag": {
            "type": "string",
            "enum": ["green", "amber", "red"],
            "description": "Overall delivery health this week.",
        },
        "asks_of_client": {
            "type": "array",
            "description": "What the client must do, and by when.",
            "items": {"type": "string"},
        },
    }
)


class WeeklyClientStatusTask(AgentTask):
    name = "weekly_client_status"
    title = "Weekly client status"
    description = (
        "Aggregate sprint progress, velocity, scope delta, risks and decisions "
        "into a client-ready status report."
    )

    autonomy = AutonomyLevel.L2_DRAFT_APPROVE
    model_tier = ModelTier.NARRATIVE  # the brief's "route to Claude" case
    approval_kind = ApprovalKind.WEEKLY_STATUS
    posts_to_channel = False
    auto_execute_writes = False

    def instructions(self) -> str:
        return INSTRUCTIONS

    async def gather(self, ctx: TaskContext) -> dict[str, Any]:
        project_key = ctx.engagement.jira_project_key or ctx.engagement.slug.upper()
        snapshot = await ctx.registry.jira.get_sprint_snapshot(
            project_key, board_id=ctx.engagement.jira_board_id
        )
        velocity = await ctx.registry.jira.get_velocity(project_key)

        activity = None
        if ctx.engagement.github_repo:
            # The reporting window, in order of preference: what the service
            # computed, when the sprint started, otherwise the last seven days.
            since = (
                ctx.prior.get("period_start_utc")
                or snapshot.sprint_start
                or utc_now() - timedelta(days=7)
            )
            activity = await ctx.registry.github.get_activity(
                ctx.engagement.github_repo, since=since
            )

        raid_rows = []
        if ctx.engagement.raid_workbook_url:
            raid_rows = await ctx.registry.storage.read_raid_rows(
                ctx.engagement.raid_workbook_url
            )

        return {
            "snapshot": snapshot,
            "velocity": velocity,
            "activity": activity,
            "raid_rows": raid_rows,
            "prior_report": ctx.prior.get("prior_report"),
            "standups": ctx.prior.get("standups", []),
        }

    async def reason(self, ctx: TaskContext, evidence: dict[str, Any]) -> TaskResult:
        snapshot = evidence["snapshot"]
        velocity = evidence["velocity"]
        activity = evidence.get("activity")
        raid_rows = evidence.get("raid_rows") or []

        totals = snapshot.totals()
        lines = [
            f"Sprint {snapshot.sprint_name}: {totals['delivered']} of "
            f"{totals['issues']} items done, {totals['blocked']} blocked",
            f"Points committed {totals['points_committed']}, "
            f"delivered {totals['points_delivered']}",
            f"Average velocity over recent sprints: {velocity.average:.1f} points",
        ]
        lines += [
            f"{issue.key} — {issue.summary} | {issue.status} | owner {issue.owner}"
            for issue in snapshot.issues
        ]
        if activity:
            lines += [
                f"commit {commit.short_sha} — {commit.title}"
                for commit in activity.commits
            ]
        lines += [
            f"RAID [{row.type}/{row.severity or 'unrated'}] {row.title} "
            f"(status {row.status or 'open'}, owner {row.owner or 'unassigned'})"
            for row in raid_rows
        ]

        citations = snapshot.citations()
        if activity:
            citations += activity.citations()

        extra: dict[str, str] = {}
        if evidence.get("prior_report"):
            extra["last_weeks_report"] = str(evidence["prior_report"])[:4000]
        standups = evidence.get("standups") or []
        if standups:
            extra["this_weeks_standups"] = "\n".join(
                f"- {entry}" for entry in standups[:14]
            )

        period_end = ctx.for_date
        period_start = period_end - timedelta(days=6)

        prompt = self.build_user_prompt(
            instruction=(
                f"Write the client status report for "
                f"{period_start.isoformat()} to {period_end.isoformat()}."
            ),
            evidence_lines=lines,
            citations=citations,
            extra_sections=extra,
        )

        response = await self.ask_json(
            ctx, prompt=prompt, schema=STATUS_SCHEMA, schema_name="weekly_status"
        )
        data = response.data
        content = str(data.get("summary_markdown", "")).strip()

        return TaskResult(
            task_name=self.name,
            claims=self.parse_claims(data.get("claims")),
            evidence=citations,
            artifact={
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "title": (
                    f"{ctx.engagement.name} — status "
                    f"{period_start.isoformat()} to {period_end.isoformat()}"
                ),
                "content_markdown": content,
                "sections": {
                    "headline": data.get("headline", ""),
                    "status_rag": data.get("status_rag", "amber"),
                    "asks_of_client": data.get("asks_of_client", []),
                    "metrics": totals,
                    "velocity_average": velocity.average,
                    "open_raid_count": len(raid_rows),
                },
            },
            summary_markdown=content,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
