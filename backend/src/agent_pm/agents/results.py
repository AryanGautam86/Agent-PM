"""What an agent task returns.

Deliberately not a Pydantic model: this crosses no HTTP boundary. Services map
it onto ORM rows and API schemas. Keeping it a plain dataclass lets it carry
:class:`~agent_pm.core.grounding.Claim` objects directly, so the grounding
check operates on the same values the task produced rather than on a
round-tripped copy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_pm.core.enums import ApprovalKind
from agent_pm.core.grounding import Citation, Claim
from agent_pm.integrations.teams.base import ChannelCard


@dataclass(slots=True)
class ProposedWrite:
    """A change the task wants to make to an external system.

    Never executed by the task. The runner turns it into an ``Approval`` row
    (L1/L2) or hands it to the service for immediate execution (L3/L4).
    ``payload`` is executed verbatim on approval — see ``models/approval.py``.
    """

    kind: ApprovalKind
    title: str
    payload: dict[str, Any]
    rationale: str | None = None
    citations: list[Citation] = field(default_factory=list)

    def citation_dicts(self) -> list[dict[str, Any]]:
        return [
            {"kind": c.kind, "ref": c.ref, "url": c.url} for c in self.citations
        ]


@dataclass(slots=True)
class TaskResult:
    """The outcome of one task run."""

    task_name: str

    claims: list[Claim] = field(default_factory=list)
    """Every assertion the task wants to publish. Validated against
    ``evidence`` before anything leaves the process."""

    evidence: list[Citation] = field(default_factory=list)
    """The full set of references the task actually saw. A citation outside
    this set is treated as fabricated."""

    artifact: dict[str, Any] = field(default_factory=dict)
    """Domain payload for the service to persist (standup fields, report
    sections, …). Shape is a contract between one task and one service."""

    card: ChannelCard | None = None
    """Optional channel post. Only sent when autonomy permits."""

    proposed_writes: list[ProposedWrite] = field(default_factory=list)

    summary_markdown: str = ""
    notes: list[str] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str | None = None

    # --- provenance, filled by the runner --------------------------------
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    grounding_ratio: float | None = None

    def citation_dicts(self) -> list[dict[str, Any]]:
        return [{"kind": c.kind, "ref": c.ref, "url": c.url} for c in self.evidence]

    @classmethod
    def skip(cls, task_name: str, reason: str) -> TaskResult:
        return cls(task_name=task_name, skipped=True, skip_reason=reason)
