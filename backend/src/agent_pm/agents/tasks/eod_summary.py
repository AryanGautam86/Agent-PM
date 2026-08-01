"""End-of-day summary.

Brief: *at end of day, post what shipped, what's pending, what's blocked.*
Trigger 17:30 daily, autonomy L3. Emits ``pm_eod_summary`` for downstream
consumers.

Differs from the morning task in that GitHub is a first-class input: "shipped"
is a claim about code, and Jira status alone is weak evidence for it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from agent_pm.agents.context import TaskContext
from agent_pm.agents.prompts import narrative_schema
from agent_pm.agents.results import TaskResult
from agent_pm.agents.tasks.standup_base import StandupTaskBase
from agent_pm.core.clock import utc_now
from agent_pm.core.logging import get_logger

logger = get_logger(__name__)

INSTRUCTIONS = """\
Write the end-of-day summary for the pod.

Structure it as:
1. Shipped — what actually completed today. A ticket counts as shipped only if
   its status is done, or a merged pull request references it. Cite both when
   you have both.
2. In flight — what moved but did not finish, and whether it lands tomorrow.
3. Blocked — what is stuck, for how long, and who needs to act. If a blocker
   has been open more than two days, say so explicitly.

If nothing shipped, say that plainly. A quiet day reported honestly is more
useful than a padded one. Aim for under 180 words.
"""

EOD_SCHEMA = narrative_schema(
    {
        "shipped_issue_keys": {
            "type": "array",
            "description": "Keys you are asserting completed today. Each must "
            "appear in allowed_citations.",
            "items": {"type": "string"},
        },
        "needs_attention": {
            "type": "array",
            "description": "Items the PO should look at before tomorrow.",
            "items": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["issue_key", "reason"],
            },
        },
    }
)


class EodSummaryTask(StandupTaskBase):
    name = "eod_summary"
    title = "End-of-day summary"
    description = "Post what shipped, what is pending, and what is blocked."

    def instructions(self) -> str:
        return INSTRUCTIONS

    async def gather(self, ctx: TaskContext) -> dict[str, Any]:
        snapshot = await self.fetch_snapshot(ctx)

        activity = None
        if ctx.engagement.github_repo:
            # Since this morning's post, not a rolling 24h, so a late-evening
            # re-run does not re-report last night's commits as today's.
            since = ctx.prior.get("since") or utc_now() - timedelta(hours=12)
            activity = await ctx.registry.github.get_activity(
                ctx.engagement.github_repo, since=since
            )

        return {
            "snapshot": snapshot,
            "activity": activity,
            "morning_post": ctx.prior.get("morning_post"),
            "meeting_outcomes": ctx.prior.get("meeting_outcomes", []),
        }

    async def reason(self, ctx: TaskContext, evidence: dict[str, Any]) -> TaskResult:
        snapshot = evidence["snapshot"]
        activity = evidence.get("activity")

        if not snapshot.issues:
            return TaskResult.skip(self.name, "No issues in the active sprint.")

        lines = self.snapshot_evidence(snapshot) + self.commit_lines(activity)

        extra: dict[str, str] = {}
        if evidence.get("morning_post"):
            extra["this_mornings_plan"] = str(evidence["morning_post"])[:2000]
        outcomes = evidence.get("meeting_outcomes") or []
        if outcomes:
            extra["meeting_outcomes_today"] = "\n".join(
                f"- {item}" for item in outcomes[:20]
            )

        citations = self.collect_citations(snapshot, activity)

        prompt = self.build_user_prompt(
            instruction=f"Write the end-of-day summary for {ctx.for_date.isoformat()}.",
            evidence_lines=lines,
            citations=citations,
            extra_sections=extra,
        )

        response = await self.ask_json(
            ctx, prompt=prompt, schema=EOD_SCHEMA, schema_name="eod_summary"
        )
        data = response.data
        summary = str(data.get("summary_markdown", "")).strip()

        artifact = self.build_artifact(snapshot, activity)
        artifact["shipped_issue_keys"] = data.get("shipped_issue_keys", [])
        artifact["needs_attention"] = data.get("needs_attention", [])

        delivered = len(snapshot.delivered)
        card = self.build_card(
            title=f"End of day — {ctx.engagement.name}",
            subtitle=f"{delivered} done · {len(snapshot.pending)} pending · "
            f"{len(snapshot.blockers)} blocked",
            summary_markdown=summary,
            snapshot=snapshot,
        )

        return TaskResult(
            task_name=self.name,
            claims=self.parse_claims(data.get("claims")),
            evidence=citations,
            artifact=artifact,
            card=card,
            summary_markdown=summary,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
