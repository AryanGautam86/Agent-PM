"""Agent task base class.

A task declares what it is allowed to do and implements two steps:

``gather``  pull read-only evidence from the integration ports
``reason``  turn that evidence into a :class:`TaskResult`

It does not decide whether its proposed writes execute, does not open database
transactions, and does not post to a channel. Those belong to the runner
(``services/agent_runner.py``), which is the only component that can act on a
result — and the only place autonomy is enforced.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from agent_pm.agents.context import TaskContext
from agent_pm.agents.prompts import (
    citation_catalogue,
    evidence_block,
    system_prompt,
)
from agent_pm.agents.results import TaskResult
from agent_pm.core.enums import ApprovalKind, AutonomyLevel, ModelTier
from agent_pm.core.grounding import Citation, Claim
from agent_pm.core.logging import get_logger
from agent_pm.integrations.llm.base import LLMMessage, LLMResponse

logger = get_logger(__name__)


class AgentTask(ABC):
    """One row of the brief's task catalog."""

    name: ClassVar[str]
    title: ClassVar[str]
    description: ClassVar[str]

    autonomy: ClassVar[AutonomyLevel] = AutonomyLevel.L2_DRAFT_APPROVE
    """Declared level. The engagement's ceiling can lower it, never raise it."""

    model_tier: ClassVar[ModelTier] = ModelTier.STRUCTURED
    requires_citations: ClassVar[bool] = True
    approval_kind: ClassVar[ApprovalKind | None] = None

    posts_to_channel: ClassVar[bool] = False
    """Whether a produced card is posted. Only honoured at L3 and above; at
    L1/L2 the result stays in the app for a human to look at."""

    auto_execute_writes: ClassVar[bool] = False
    """Whether ``proposed_writes`` may execute without an approval row.

    Default False, and it stays False for anything touching Jira or the RAID
    log — the brief's "never auto-updates a system without explicit PO
    confirmation" is expressed here. A task being L3 means it may *post*
    autonomously, not that it may *write* autonomously."""

    # ---- contract --------------------------------------------------------

    @abstractmethod
    async def gather(self, ctx: TaskContext) -> dict[str, Any]:
        """Read-only evidence collection. Must not write anywhere."""

    @abstractmethod
    async def reason(self, ctx: TaskContext, evidence: dict[str, Any]) -> TaskResult:
        """Turn evidence into a result. Must not write anywhere."""

    def instructions(self) -> str:
        """Task-specific half of the system prompt."""
        return self.description

    # ---- helpers for subclasses -----------------------------------------

    def build_system_prompt(self, ctx: TaskContext) -> str:
        return system_prompt(ctx.engagement, self.instructions())

    @staticmethod
    def build_user_prompt(
        *,
        instruction: str,
        evidence_lines: list[str],
        citations: list[Citation],
        extra_sections: dict[str, str] | None = None,
    ) -> str:
        parts = [instruction.strip(), "", evidence_block(evidence_lines), ""]
        for heading, body in (extra_sections or {}).items():
            parts.extend([f"<{heading}>", body, f"</{heading}>", ""])
        parts.append(citation_catalogue(citations))
        return "\n".join(parts)

    async def ask_json(
        self,
        ctx: TaskContext,
        *,
        prompt: str,
        schema: dict[str, Any],
        schema_name: str = "result",
    ) -> LLMResponse:
        return await ctx.registry.llm.complete_json(
            system=self.build_system_prompt(ctx),
            messages=[LLMMessage(role="user", content=prompt)],
            model=ctx.registry.model_for(self.model_tier),
            schema=schema,
            schema_name=schema_name,
        )

    async def ask_text(self, ctx: TaskContext, *, prompt: str) -> LLMResponse:
        return await ctx.registry.llm.complete(
            system=self.build_system_prompt(ctx),
            messages=[LLMMessage(role="user", content=prompt)],
            model=ctx.registry.model_for(self.model_tier),
        )

    @staticmethod
    def parse_claims(raw: Any) -> list[Claim]:
        """Convert the model's claim objects into grounding-policy input.

        Anything malformed becomes an uncited claim rather than being dropped —
        a claim we cannot verify must fail the grounding check, not vanish
        from it.
        """
        claims: list[Claim] = []
        for entry in raw or []:
            if not isinstance(entry, dict):
                continue
            text = str(entry.get("text", "")).strip()
            if not text:
                continue
            citations = tuple(
                Citation(kind=str(c.get("kind", "jira")), ref=str(c.get("ref", "")))
                for c in entry.get("citations", [])
                if isinstance(c, dict) and c.get("ref")
            )
            claims.append(Claim(text=text, citations=citations))
        return claims

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} {self.name} autonomy={self.autonomy.value}>"
