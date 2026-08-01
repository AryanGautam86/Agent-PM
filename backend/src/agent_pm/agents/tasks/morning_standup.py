"""Morning sprint plan.

Brief: *at start of day, post the sprint plan + committed/delivered/pending
counts by person + current blockers.* Trigger 08:00 daily, autonomy L3 —
posts without asking, PO reviews after.
"""

from __future__ import annotations

from typing import Any

from agent_pm.agents.context import TaskContext
from agent_pm.agents.prompts import narrative_schema
from agent_pm.agents.results import TaskResult
from agent_pm.agents.tasks.standup_base import StandupTaskBase
from agent_pm.core.logging import get_logger

logger = get_logger(__name__)

INSTRUCTIONS = """\
Write the morning sprint plan for the pod, to be read before standup.

Structure it as:
1. One line on where the sprint stands — day, scope, whether it is on track.
2. What matters today, ranked by impact. Name the person and the ticket.
3. Blockers, oldest first, each with who owns clearing it and what it is
   holding up. This is the part the PO reads first.

Do not restate the per-person table; it is rendered separately below your
text. Refer to it, do not duplicate it. Aim for under 150 words.
"""

PLAN_SCHEMA = narrative_schema(
    {
        "headline": {
            "type": "string",
            "description": "One sentence on sprint health. Under 100 characters.",
        },
        "focus_today": {
            "type": "array",
            "description": "Up to three things the pod should prioritise today.",
            "items": {
                "type": "object",
                "properties": {
                    "person": {"type": "string"},
                    "issue_key": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["person", "issue_key", "why"],
            },
        },
    }
)


class MorningSprintPlanTask(StandupTaskBase):
    name = "morning_sprint_plan"
    title = "Morning sprint plan"
    description = (
        "Post the sprint plan with committed/delivered/pending counts per "
        "person and the current blockers."
    )

    def instructions(self) -> str:
        return INSTRUCTIONS

    async def gather(self, ctx: TaskContext) -> dict[str, Any]:
        """Jira is the only required source.

        The RAID log and yesterday's EOD are context, not inputs the post
        depends on — a missing workbook must not stop the morning post.
        """
        snapshot = await self.fetch_snapshot(ctx)

        raid_rows = []
        if ctx.engagement.raid_workbook_url:
            raid_rows = await ctx.registry.storage.read_raid_rows(
                ctx.engagement.raid_workbook_url
            )

        return {
            "snapshot": snapshot,
            "raid_rows": raid_rows,
            "prior_eod": ctx.prior.get("prior_eod"),
        }

    async def reason(self, ctx: TaskContext, evidence: dict[str, Any]) -> TaskResult:
        snapshot = evidence["snapshot"]

        if not snapshot.issues:
            return TaskResult.skip(
                self.name, "No issues in the active sprint — nothing to plan."
            )

        lines = self.snapshot_evidence(snapshot)
        extra: dict[str, str] = {}

        raid_rows = evidence.get("raid_rows") or []
        if raid_rows:
            extra["raid_log"] = "\n".join(
                f"- [{row.type}] {row.title} (status: {row.status or 'unknown'}, "
                f"owner: {row.owner or 'unassigned'})"
                for row in raid_rows
            )

        prior = evidence.get("prior_eod")
        if prior:
            extra["yesterday_eod"] = str(prior)[:2000]

        prompt = self.build_user_prompt(
            instruction=(
                f"Write the morning sprint plan for {ctx.for_date.isoformat()}."
            ),
            evidence_lines=lines,
            citations=self.collect_citations(snapshot),
            extra_sections=extra,
        )

        response = await self.ask_json(
            ctx, prompt=prompt, schema=PLAN_SCHEMA, schema_name="morning_plan"
        )
        data = response.data

        summary = str(data.get("summary_markdown", "")).strip()
        headline = str(data.get("headline", "")).strip()

        artifact = self.build_artifact(snapshot)
        artifact["focus_today"] = data.get("focus_today", [])
        artifact["headline"] = headline

        card = self.build_card(
            title=f"Morning sprint plan — {ctx.engagement.name}",
            subtitle=headline or snapshot.sprint_name,
            summary_markdown=summary,
            snapshot=snapshot,
        )

        return TaskResult(
            task_name=self.name,
            claims=self.parse_claims(data.get("claims")),
            evidence=self.collect_citations(snapshot),
            artifact=artifact,
            card=card,
            summary_markdown=summary,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
