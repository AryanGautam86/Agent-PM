"""RAID log read and gap detection.

Brief: *scan the RAID log against current Jira blockers; flag blockers NOT in
RAID.* Autonomy L3 — the scan and the card are autonomous; every resulting
workbook write is gated on a PO approval.

The gap detection itself is deliberately deterministic set arithmetic, not a
model judgement: "is DEMO-105 in the RAID log" has a right answer, and a model
that occasionally says no when it means yes would generate approval spam. The
model is used only for the part that needs judgement — proposing a plausible
mitigation for a gap that is real.
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
For each Jira blocker that is missing from the RAID log, propose the RAID entry
it should become.

For each one give:
- a title a client would understand, not the raw ticket summary;
- the delivery consequence if it is not cleared;
- a concrete first mitigation step, naming who acts.

Judge severity from how long it has been blocked and what it holds up. Do not
propose entries for blockers already in the log, and do not invent blockers.
"""

GAP_SCHEMA = {
    "type": "object",
    "properties": {
        "gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "mitigation": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                    "raid_type": {
                        "type": "string",
                        "enum": ["risk", "issue", "dependency", "assumption"],
                    },
                },
                "required": [
                    "issue_key",
                    "title",
                    "description",
                    "mitigation",
                    "severity",
                    "raid_type",
                ],
            },
        },
        "summary_markdown": {"type": "string"},
    },
    "required": ["gaps", "summary_markdown"],
}

# A blocker older than this is proposed as an issue rather than a risk: it has
# already materialised.
ISSUE_AGE_DAYS = 5.0


class RaidGapScanTask(AgentTask):
    name = "raid_gap_scan"
    title = "RAID gap detection"
    description = (
        "Compare current Jira blockers against the RAID log and propose "
        "entries for anything missing."
    )

    autonomy = AutonomyLevel.L3_ACT_REVIEW
    model_tier = ModelTier.STRUCTURED
    approval_kind = ApprovalKind.RAID_GAP_ADD
    posts_to_channel = True
    auto_execute_writes = False

    def instructions(self) -> str:
        return INSTRUCTIONS

    async def gather(self, ctx: TaskContext) -> dict[str, Any]:
        snapshot = await ctx.registry.jira.get_sprint_snapshot(
            ctx.engagement.jira_project_key or ctx.engagement.slug.upper(),
            board_id=ctx.engagement.jira_board_id,
        )

        workbook_rows = []
        if ctx.engagement.raid_workbook_url:
            workbook_rows = await ctx.registry.storage.read_raid_rows(
                ctx.engagement.raid_workbook_url
            )

        # Two sources of "already covered": the workbook itself, and the
        # source_refs of items we hold locally (which may include entries
        # approved but not yet synced).
        covered: set[str] = {
            row.source_ref for row in workbook_rows if row.source_ref
        }
        covered |= set(ctx.prior.get("raid_source_refs", []))

        # A workbook row can also mention the key in its text.
        haystack = " ".join(
            f"{row.title} {row.description or ''}" for row in workbook_rows
        )

        return {
            "snapshot": snapshot,
            "workbook_rows": workbook_rows,
            "covered_refs": covered,
            "workbook_text": haystack,
        }

    async def reason(self, ctx: TaskContext, evidence: dict[str, Any]) -> TaskResult:
        snapshot = evidence["snapshot"]
        covered: set[str] = evidence["covered_refs"]
        workbook_text: str = evidence["workbook_text"]

        gaps: list[JiraIssue] = [
            issue
            for issue in snapshot.blockers
            if issue.key not in covered and issue.key not in workbook_text
        ]

        if not gaps:
            return TaskResult(
                task_name=self.name,
                evidence=snapshot.citations(),
                artifact={"gap_count": 0, "checked": len(snapshot.blockers)},
                summary_markdown=(
                    f"All {len(snapshot.blockers)} current blockers are represented "
                    "in the RAID log."
                ),
                claims=[
                    Claim(
                        text=f"{issue.key} is already tracked in the RAID log.",
                        citations=(issue.citation(),),
                    )
                    for issue in snapshot.blockers
                ],
            )

        prompt = self.build_user_prompt(
            instruction=(
                f"{len(gaps)} blocker(s) are missing from the RAID log. "
                "Propose the RAID entry for each."
            ),
            evidence_lines=[
                f"{issue.key} — {issue.summary} | owner: {issue.owner} | "
                f"status: {issue.status} | blocked "
                f"{issue.blocked_age_days or 0:.0f}d"
                for issue in gaps
            ],
            citations=[issue.citation() for issue in gaps],
            extra_sections={
                "existing_raid_log": "\n".join(
                    f"- [{row.type}] {row.title}"
                    for row in evidence["workbook_rows"]
                )
                or "(empty)"
            },
        )

        response = await self.ask_json(
            ctx, prompt=prompt, schema=GAP_SCHEMA, schema_name="raid_gaps"
        )

        by_key = {issue.key: issue for issue in gaps}
        proposals = self._build_proposals(response.data.get("gaps", []), by_key)

        # Fallback: if the model returned nothing usable, still surface the
        # gaps. A missed RAID entry is worse than a terse one.
        if not proposals:
            proposals = self._build_proposals(
                [self._default_proposal(issue) for issue in gaps], by_key
            )

        claims = [
            Claim(
                text=f"{issue.key} is a current blocker with no RAID entry.",
                citations=(issue.citation(),),
            )
            for issue in gaps
        ]

        return TaskResult(
            task_name=self.name,
            claims=claims,
            evidence=snapshot.citations(),
            artifact={
                "gap_count": len(proposals),
                "checked": len(snapshot.blockers),
                "gap_keys": [issue.key for issue in gaps],
            },
            card=self._build_card(ctx, proposals),
            proposed_writes=proposals,
            summary_markdown=str(response.data.get("summary_markdown", "")).strip()
            or f"{len(proposals)} blocker(s) missing from the RAID log.",
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )

    # ---- internals -------------------------------------------------------

    @staticmethod
    def _default_proposal(issue: JiraIssue) -> dict[str, Any]:
        age = issue.blocked_age_days or 0.0
        return {
            "issue_key": issue.key,
            "title": issue.summary,
            "description": (
                f"{issue.key} has been blocked for {age:.0f} day(s); "
                f"owned by {issue.owner}."
            ),
            "mitigation": f"{issue.owner} to identify what is blocking {issue.key}.",
            "severity": Severity.HIGH.value if age >= 3 else Severity.MEDIUM.value,
            "raid_type": (
                RaidType.ISSUE.value if age >= ISSUE_AGE_DAYS else RaidType.RISK.value
            ),
        }

    def _build_proposals(
        self, raw_gaps: list[Any], by_key: dict[str, JiraIssue]
    ) -> list[ProposedWrite]:
        proposals: list[ProposedWrite] = []
        seen: set[str] = set()

        for entry in raw_gaps:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("issue_key", "")).strip()
            # Only propose for blockers we actually identified — this is where
            # a hallucinated ticket would otherwise become a workbook write.
            issue = by_key.get(key)
            if issue is None or key in seen:
                continue
            seen.add(key)

            payload = {
                "type": str(entry.get("raid_type", RaidType.RISK.value)),
                "title": str(entry.get("title") or issue.summary),
                "description": str(entry.get("description", "")),
                "mitigation": str(entry.get("mitigation", "")),
                "severity": str(entry.get("severity", Severity.MEDIUM.value)),
                "owner_label": issue.owner,
                "source": "jira_gap_scan",
                "source_ref": key,
            }
            proposals.append(
                ProposedWrite(
                    kind=ApprovalKind.RAID_GAP_ADD,
                    title=f"Add {key} to the RAID log",
                    payload=payload,
                    rationale=(
                        f"{key} has been blocked for "
                        f"{issue.blocked_age_days or 0:.0f} day(s) and does not "
                        "appear in the RAID log."
                    ),
                    citations=[issue.citation()],
                )
            )
        return proposals

    @staticmethod
    def _build_card(ctx: TaskContext, proposals: list[ProposedWrite]) -> ChannelCard:
        return ChannelCard(
            title=f"RAID gaps — {ctx.engagement.name}",
            subtitle=f"{len(proposals)} blocker(s) not in the RAID log",
            accent="warning",
            sections=[
                CardSection(
                    body_markdown="\n".join(
                        f"- **{p.payload['source_ref']}** {p.payload['title']} "
                        f"_(proposed {p.payload['type']}, {p.payload['severity']})_"
                        for p in proposals
                    )
                ),
                CardSection(
                    body_markdown=(
                        "_Nothing has been written. Approve each entry in the "
                        "Agent-PM approvals queue._"
                    )
                ),
            ],
        )
