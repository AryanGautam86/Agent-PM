"""Blocker → risk promotion.

Brief: *blocker > 2 days old → propose promoting to risk in the RAID log with
mitigation.* Autonomy L2 — drafts only, PO confirms.

Distinct from the gap scan: that one asks "is this blocker represented at
all?", this one asks "has this blocker aged into something the client should
see as a risk?". A blocker can be in the RAID log as an issue and still warrant
promotion.
"""

from __future__ import annotations

from typing import Any

from agent_pm.agents.base import AgentTask
from agent_pm.agents.context import TaskContext
from agent_pm.agents.results import ProposedWrite, TaskResult
from agent_pm.core.enums import ApprovalKind, AutonomyLevel, ModelTier, RaidType, Severity
from agent_pm.core.grounding import Claim
from agent_pm.core.logging import get_logger
from agent_pm.integrations.jira.models import JiraIssue
from agent_pm.integrations.teams.base import CardSection, ChannelCard

logger = get_logger(__name__)

INSTRUCTIONS = """\
These blockers have aged past the promotion threshold. For each, write the risk
as the client should see it.

Give a title in delivery terms (what is at stake, not what the ticket says), a
one-line statement of the impact if it is not cleared this sprint, and a
mitigation naming the owner and the next concrete step.

Severity should reflect delivery impact, not how annoying the blocker is.
"""

PROMOTION_SCHEMA = {
    "type": "object",
    "properties": {
        "promotions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string"},
                    "risk_title": {"type": "string"},
                    "impact": {"type": "string"},
                    "mitigation": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                },
                "required": [
                    "issue_key",
                    "risk_title",
                    "impact",
                    "mitigation",
                    "severity",
                ],
            },
        },
        "summary_markdown": {"type": "string"},
    },
    "required": ["promotions", "summary_markdown"],
}


class BlockerRiskPromotionTask(AgentTask):
    name = "blocker_risk_promotion"
    title = "Blocker to risk promotion"
    description = (
        "Propose promoting long-running blockers to RAID risks, with mitigation."
    )

    autonomy = AutonomyLevel.L2_DRAFT_APPROVE
    model_tier = ModelTier.STRUCTURED
    approval_kind = ApprovalKind.RISK_PROMOTION
    posts_to_channel = False
    auto_execute_writes = False

    def instructions(self) -> str:
        return INSTRUCTIONS

    async def gather(self, ctx: TaskContext) -> dict[str, Any]:
        snapshot = await ctx.registry.jira.get_sprint_snapshot(
            ctx.engagement.jira_project_key or ctx.engagement.slug.upper(),
            board_id=ctx.engagement.jira_board_id,
        )
        threshold = float(ctx.param("age_threshold_days", 2))

        # Already promoted, so we do not re-propose every single day.
        promoted: set[str] = set(ctx.prior.get("promoted_refs", []))

        candidates = [
            issue
            for issue in snapshot.blockers
            if (issue.blocked_age_days or 0.0) >= threshold and issue.key not in promoted
        ]
        return {
            "snapshot": snapshot,
            "candidates": candidates,
            "threshold": threshold,
        }

    async def reason(self, ctx: TaskContext, evidence: dict[str, Any]) -> TaskResult:
        candidates: list[JiraIssue] = evidence["candidates"]
        threshold: float = evidence["threshold"]
        snapshot = evidence["snapshot"]

        if not candidates:
            return TaskResult.skip(
                self.name,
                f"No blockers older than {threshold:.0f} day(s) awaiting promotion.",
            )

        prompt = self.build_user_prompt(
            instruction=(
                f"{len(candidates)} blocker(s) have been blocked for "
                f"{threshold:.0f} days or more. Write each as a risk."
            ),
            evidence_lines=[
                f"{issue.key} — {issue.summary} | owner: {issue.owner} | "
                f"blocked {issue.blocked_age_days or 0:.0f}d | status: {issue.status}"
                for issue in candidates
            ],
            citations=[issue.citation() for issue in candidates],
        )

        response = await self.ask_json(
            ctx, prompt=prompt, schema=PROMOTION_SCHEMA, schema_name="risk_promotions"
        )

        by_key = {issue.key: issue for issue in candidates}
        proposals: list[ProposedWrite] = []

        for entry in response.data.get("promotions", []):
            if not isinstance(entry, dict):
                continue
            issue = by_key.get(str(entry.get("issue_key", "")).strip())
            if issue is None:
                continue
            age = issue.blocked_age_days or 0.0
            proposals.append(
                ProposedWrite(
                    kind=ApprovalKind.RISK_PROMOTION,
                    title=f"Promote {issue.key} to a RAID risk",
                    payload={
                        "type": RaidType.RISK.value,
                        "title": str(entry.get("risk_title") or issue.summary),
                        "description": str(entry.get("impact", "")),
                        "mitigation": str(entry.get("mitigation", "")),
                        "severity": str(entry.get("severity", Severity.HIGH.value)),
                        "owner_label": issue.owner,
                        "source": "blocker_promotion",
                        "source_ref": issue.key,
                    },
                    rationale=f"Blocked for {age:.0f} days (threshold {threshold:.0f}).",
                    citations=[issue.citation()],
                )
            )

        claims = [
            Claim(
                text=(
                    f"{issue.key} has been blocked for "
                    f"{issue.blocked_age_days or 0:.0f} days."
                ),
                citations=(issue.citation(),),
            )
            for issue in candidates
        ]

        return TaskResult(
            task_name=self.name,
            claims=claims,
            evidence=snapshot.citations(),
            artifact={"candidate_keys": [issue.key for issue in candidates]},
            card=ChannelCard(
                title=f"Proposed risk promotions — {ctx.engagement.name}",
                subtitle=f"{len(proposals)} blocker(s) aged past {threshold:.0f} days",
                accent="warning",
                sections=[
                    CardSection(
                        body_markdown="\n".join(
                            f"- **{p.payload['source_ref']}** → {p.payload['title']}"
                            for p in proposals
                        )
                        or "_None._"
                    )
                ],
            ),
            proposed_writes=proposals,
            summary_markdown=str(response.data.get("summary_markdown", "")).strip(),
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
