"""Meeting-driven update flow.

Brief: *consume ``meeting_outcome`` from the Meeting Agent; propose Jira AND
RAID updates with HITL.* Autonomy L2 — everything is a draft.

The A2A contract is the whole point of this task: it reads the structured
envelope only. Raw transcripts never reach it, so consent is enforced upstream
once rather than re-litigated here, and the two agents cannot drift as long as
the envelope schema holds.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agent_pm.agents.base import AgentTask
from agent_pm.agents.context import TaskContext
from agent_pm.agents.results import ProposedWrite, TaskResult
from agent_pm.core.enums import ApprovalKind, AutonomyLevel, ModelTier, RaidType, Severity
from agent_pm.core.grounding import Citation, Claim
from agent_pm.core.logging import get_logger

logger = get_logger(__name__)

INSTRUCTIONS = """\
A meeting has produced decisions, actions and risks. Turn them into proposed
system updates.

For each decision that changes the state of a ticket, propose a Jira comment
recording the decision and who made it.
For each risk raised, propose a RAID entry.
For each action, keep the owner and due date exactly as recorded — do not
invent either. If an action has no owner, say so rather than guessing.

Cite the transcript timestamp or item id behind every proposal.
"""

MEETING_SCHEMA = {
    "type": "object",
    "properties": {
        "jira_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string"},
                    "comment": {"type": "string"},
                    "reason": {"type": "string"},
                    "citation_ref": {"type": "string"},
                },
                "required": ["issue_key", "comment", "reason", "citation_ref"],
            },
        },
        "raid_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "mitigation": {"type": "string"},
                    "raid_type": {
                        "type": "string",
                        "enum": ["risk", "issue", "dependency", "assumption"],
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                    },
                    "owner": {"type": "string"},
                    "citation_ref": {"type": "string"},
                },
                "required": [
                    "title",
                    "description",
                    "raid_type",
                    "severity",
                    "citation_ref",
                ],
            },
        },
        "summary_markdown": {"type": "string"},
    },
    "required": ["jira_updates", "raid_updates", "summary_markdown"],
}


class MeetingOutcome(BaseModel):
    """Version 1 of the Meeting Agent's envelope payload."""

    meeting_id: str | None = None
    title: str | None = None
    occurred_at: str | None = None
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[dict[str, Any]] = Field(default_factory=list)

    def evidence_lines(self) -> list[str]:
        lines: list[str] = []
        for index, decision in enumerate(self.decisions):
            ref = decision.get("timestamp") or f"decision-{index}"
            lines.append(
                f"[{ref}] DECISION: {decision.get('text', '')} "
                f"(by {decision.get('owner', 'unknown')})"
            )
        for index, action in enumerate(self.actions):
            ref = action.get("timestamp") or f"action-{index}"
            lines.append(
                f"[{ref}] ACTION: {action.get('text', '')} "
                f"(owner {action.get('owner', 'unassigned')}, "
                f"due {action.get('due', 'unspecified')})"
            )
        for index, risk in enumerate(self.risks):
            ref = risk.get("timestamp") or f"risk-{index}"
            lines.append(f"[{ref}] RISK: {risk.get('text', '')}")
        return lines

    def citations(self) -> list[Citation]:
        refs = []
        for group, prefix in (
            (self.decisions, "decision"),
            (self.actions, "action"),
            (self.risks, "risk"),
        ):
            for index, item in enumerate(group):
                refs.append(
                    Citation(
                        kind="transcript",
                        ref=str(item.get("timestamp") or f"{prefix}-{index}"),
                    )
                )
        return refs


class MeetingIntakeTask(AgentTask):
    name = "meeting_outcome_intake"
    title = "Meeting-driven updates"
    description = (
        "Turn a meeting outcome into proposed Jira and RAID updates, and "
        "capture its action items."
    )

    autonomy = AutonomyLevel.L2_DRAFT_APPROVE
    model_tier = ModelTier.STRUCTURED
    approval_kind = ApprovalKind.JIRA_UPDATE
    posts_to_channel = False
    auto_execute_writes = False

    def instructions(self) -> str:
        return INSTRUCTIONS

    async def gather(self, ctx: TaskContext) -> dict[str, Any]:
        """The envelope is supplied by the event service; nothing is fetched."""
        raw = ctx.prior.get("meeting_outcome")
        if raw is None:
            return {"outcome": None}
        outcome = (
            raw if isinstance(raw, MeetingOutcome) else MeetingOutcome.model_validate(raw)
        )

        # Known Jira keys, so a proposed comment cannot target a ticket that
        # is not in this engagement's sprint.
        snapshot = await ctx.registry.jira.get_sprint_snapshot(
            ctx.engagement.jira_project_key or ctx.engagement.slug.upper(),
            board_id=ctx.engagement.jira_board_id,
        )
        return {"outcome": outcome, "known_keys": {issue.key for issue in snapshot.issues}}

    async def reason(self, ctx: TaskContext, evidence: dict[str, Any]) -> TaskResult:
        outcome: MeetingOutcome | None = evidence.get("outcome")
        if outcome is None:
            return TaskResult.skip(self.name, "No meeting outcome supplied.")

        lines = outcome.evidence_lines()
        if not lines:
            return TaskResult.skip(self.name, "Meeting outcome contained no items.")

        citations = outcome.citations()
        known_keys: set[str] = evidence.get("known_keys", set())

        prompt = self.build_user_prompt(
            instruction=(
                f"Meeting: {outcome.title or 'untitled'}. Propose the system "
                "updates it implies."
            ),
            evidence_lines=lines,
            citations=citations,
            extra_sections={
                "known_jira_keys": ", ".join(sorted(known_keys)) or "(none)"
            },
        )

        response = await self.ask_json(
            ctx, prompt=prompt, schema=MEETING_SCHEMA, schema_name="meeting_updates"
        )
        data = response.data

        proposals: list[ProposedWrite] = []

        for entry in data.get("jira_updates", []):
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("issue_key", "")).strip()
            if key not in known_keys:
                # Refuse to comment on a ticket outside the sprint we read.
                logger.warning("meeting_intake_unknown_key", extra={"issue_key": key})
                continue
            proposals.append(
                ProposedWrite(
                    kind=ApprovalKind.JIRA_UPDATE,
                    title=f"Comment on {key}",
                    payload={
                        "issue_key": key,
                        "add_comment": str(entry.get("comment", "")),
                        "add_labels": [],
                        "remove_labels": [],
                    },
                    rationale=str(entry.get("reason", "")),
                    citations=[
                        Citation(kind="transcript", ref=str(entry.get("citation_ref", "")))
                    ],
                )
            )

        for entry in data.get("raid_updates", []):
            if not isinstance(entry, dict):
                continue
            proposals.append(
                ProposedWrite(
                    kind=ApprovalKind.RAID_UPDATE,
                    title=f"Add to RAID: {entry.get('title', '')}",
                    payload={
                        "type": str(entry.get("raid_type", RaidType.RISK.value)),
                        "title": str(entry.get("title", "")),
                        "description": str(entry.get("description", "")),
                        "mitigation": str(entry.get("mitigation", "")),
                        "severity": str(entry.get("severity", Severity.MEDIUM.value)),
                        "owner_label": entry.get("owner"),
                        "source": "meeting_outcome",
                        "source_ref": outcome.meeting_id,
                    },
                    rationale="Raised in the meeting.",
                    citations=[
                        Citation(kind="transcript", ref=str(entry.get("citation_ref", "")))
                    ],
                )
            )

        # Action items are captured directly rather than proposed: they live in
        # this application, not in a client-visible system, so no approval is
        # needed to start tracking one.
        action_items = [
            {
                "title": str(action.get("text", "")),
                "owner_label": action.get("owner"),
                "due": action.get("due"),
                "source_ref": str(
                    action.get("timestamp") or f"{outcome.meeting_id}-action-{index}"
                ),
            }
            for index, action in enumerate(outcome.actions)
            if action.get("text")
        ]

        claims = [
            Claim(text=line, citations=(citation,))
            for line, citation in zip(lines, citations, strict=False)
        ]

        return TaskResult(
            task_name=self.name,
            claims=claims,
            evidence=citations,
            artifact={
                "action_items": action_items,
                "meeting_id": outcome.meeting_id,
                "jira_proposal_count": sum(
                    1 for p in proposals if p.kind is ApprovalKind.JIRA_UPDATE
                ),
                "raid_proposal_count": sum(
                    1 for p in proposals if p.kind is ApprovalKind.RAID_UPDATE
                ),
            },
            proposed_writes=proposals,
            summary_markdown=str(data.get("summary_markdown", "")).strip(),
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
