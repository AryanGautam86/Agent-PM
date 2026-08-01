"""Prompt construction.

One persona, shared by every task, plus a strict evidence envelope. The
``<evidence>`` tag is load-bearing in two ways: it tells the model exactly which
facts it is allowed to assert, and it is what the offline fixture client echoes
back, so the same prompt produces grounded output with or without a real model.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from agent_pm.agents.context import EngagementContext
from agent_pm.core.grounding import Citation

PERSONA = """\
You are the Delivery Steward for a software services pod: a senior delivery \
manager with more than ten years in agile services delivery. You are calm, \
proactive, and you never let a follow-up slip.

How you write:
- Rank by impact. The thing that threatens the sprint goes first.
- Add the "so what". A fact without a consequence is noise.
- Be concise. A pod reads this on a phone before standup.
- Never use filler such as "as an AI" or "I hope this helps".

Rules you must not break:
1. EVIDENCE ONLY. Every claim must come from the <evidence> block. If the \
evidence does not say it, you do not say it.
2. CITE EVERYTHING. Each claim carries the identifier it came from — a Jira \
key, a commit sha, a message id, or a transcript timestamp. Never invent an \
identifier, and never cite one that is absent from the evidence.
3. NEVER CLAIM COMPLETION without an item whose status is done. "Probably \
finished" is not a status.
4. SAY WHEN YOU DO NOT KNOW. Missing evidence is itself worth reporting; \
guessing is not.
5. PROPOSE, DO NOT PERFORM. You never state that a system has been updated. \
You propose updates; a human approves them."""


def system_prompt(engagement: EngagementContext, task_instructions: str) -> str:
    client_line = f" for {engagement.client_name}" if engagement.client_name else ""
    roster = (
        "\n".join(
            f"- {member.display_name} ({member.pod_role.value})"
            for member in engagement.members
        )
        or "- (roster not configured)"
    )
    return (
        f"{PERSONA}\n\n"
        f"## Engagement\n"
        f"{engagement.name}{client_line} (identity: {engagement.agent_identity})\n\n"
        f"## Pod\n{roster}\n\n"
        f"## This task\n{task_instructions.strip()}"
    )


def evidence_block(lines: Sequence[str]) -> str:
    """Wrap facts in the tag the grounding contract depends on."""
    body = "\n".join(f"- {line}" for line in lines) if lines else "- (no evidence available)"
    return f"<evidence>\n{body}\n</evidence>"


def citation_catalogue(citations: Iterable[Citation]) -> str:
    """The exact identifiers the model is permitted to cite."""
    refs = sorted({f"{c.kind}:{c.ref}" for c in citations})
    if not refs:
        return "<allowed_citations>(none)</allowed_citations>"
    body = "\n".join(f"- {ref}" for ref in refs)
    return f"<allowed_citations>\n{body}\n</allowed_citations>"


# --------------------------------------------------------------------------
# Reusable JSON schema fragments for structured output
# --------------------------------------------------------------------------

CITATION_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": ["jira", "commit", "message", "transcript"],
        },
        "ref": {
            "type": "string",
            "description": "Identifier exactly as it appears in allowed_citations.",
        },
    },
    "required": ["kind", "ref"],
}

CLAIM_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "One assertion, one sentence."},
        "citations": {"type": "array", "items": CITATION_SCHEMA},
    },
    "required": ["text", "citations"],
}


def narrative_schema(extra_properties: dict[str, object] | None = None) -> dict[str, object]:
    """Standard envelope: prose plus the claims backing it."""
    properties: dict[str, object] = {
        "summary_markdown": {
            "type": "string",
            "description": "The post itself, in markdown. Short paragraphs or bullets.",
        },
        "claims": {
            "type": "array",
            "description": "Every factual assertion made in summary_markdown, "
            "each with the evidence it rests on.",
            "items": CLAIM_SCHEMA,
        },
    }
    if extra_properties:
        properties.update(extra_properties)
    return {
        "type": "object",
        "properties": properties,
        "required": ["summary_markdown", "claims"],
    }
