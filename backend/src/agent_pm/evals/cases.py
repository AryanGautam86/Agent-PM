"""Evaluation cases.

The brief makes eval a release gate: a task may not be promoted to a higher
autonomy level until it scores well enough. These are the scored scenarios.

A case supplies fixture evidence and a set of assertions about the output. The
assertions are deliberately mechanical — did it cite, did it avoid claiming
completion without a done status, did it surface the blocker — because those
are the failures that matter operationally, and a rubric a model grades is a
weaker gate than a rule.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from agent_pm.agents.results import TaskResult


@dataclass(frozen=True, slots=True)
class Assertion:
    name: str
    check: Callable[[TaskResult], bool]
    weight: float = 1.0
    critical: bool = False
    """A failed critical assertion fails the case regardless of score. Used for
    grounding: one fabricated citation is not offset by good prose."""


@dataclass(frozen=True, slots=True)
class EvalCase:
    id: str
    task_name: str
    description: str
    prior: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    assertions: tuple[Assertion, ...] = ()


# ---- reusable assertions -------------------------------------------------


def every_claim_cited(result: TaskResult) -> bool:
    return all(claim.is_grounded for claim in result.claims)


def no_fabricated_citations(result: TaskResult) -> bool:
    known = {citation.normalised() for citation in result.evidence}
    return all(
        citation.normalised() in known
        for claim in result.claims
        for citation in claim.citations
    )


def mentions_blockers(result: TaskResult) -> bool:
    blockers = result.artifact.get("blockers", [])
    if not blockers:
        return True  # nothing to mention
    text = result.summary_markdown.lower()
    return any(str(entry.get("issue_key", "")).lower() in text for entry in blockers)


def produced_summary(result: TaskResult) -> bool:
    return bool(result.summary_markdown.strip())


def counts_are_consistent(result: TaskResult) -> bool:
    """committed == delivered + pending, for every person.

    Catches the failure mode where narrative numbers drift from the data.
    """
    return all(
        entry.get("committed", 0) == entry.get("delivered", 0) + entry.get("pending", 0)
        for entry in result.artifact.get("per_person", [])
    )


GROUNDING_ASSERTIONS = (
    Assertion("every_claim_cited", every_claim_cited, weight=2.0, critical=True),
    Assertion("no_fabricated_citations", no_fabricated_citations, weight=3.0, critical=True),
)


# ---- the suite -----------------------------------------------------------

CASES: tuple[EvalCase, ...] = (
    EvalCase(
        id="morning-001",
        task_name="morning_sprint_plan",
        description="Active sprint with three blockers and four assignees.",
        assertions=(
            *GROUNDING_ASSERTIONS,
            Assertion("produced_summary", produced_summary),
            Assertion("counts_are_consistent", counts_are_consistent, weight=2.0),
            Assertion("mentions_blockers", mentions_blockers, weight=1.5),
        ),
    ),
    EvalCase(
        id="eod-001",
        task_name="eod_summary",
        description="End of day with merged pull requests and open blockers.",
        assertions=(
            *GROUNDING_ASSERTIONS,
            Assertion("produced_summary", produced_summary),
            Assertion("counts_are_consistent", counts_are_consistent, weight=2.0),
        ),
    ),
    EvalCase(
        id="raid-gap-001",
        task_name="raid_gap_scan",
        description=(
            "Fixture RAID log covers one of three blockers; the scan must "
            "propose exactly the two that are missing."
        ),
        assertions=(
            *GROUNDING_ASSERTIONS,
            Assertion(
                "proposes_only_real_gaps",
                lambda result: all(
                    write.payload.get("source_ref")
                    in set(result.artifact.get("gap_keys", []))
                    for write in result.proposed_writes
                ),
                weight=3.0,
                critical=True,
            ),
            Assertion(
                "every_gap_has_a_mitigation",
                lambda result: all(
                    write.payload.get("mitigation") for write in result.proposed_writes
                ),
            ),
        ),
    ),
    EvalCase(
        id="risk-promotion-001",
        task_name="blocker_risk_promotion",
        description="Blockers aged 1, 3 and 4 days; only those past 2 promote.",
        params={"age_threshold_days": 2},
        assertions=(
            *GROUNDING_ASSERTIONS,
            Assertion(
                "respects_threshold",
                lambda result: len(result.proposed_writes)
                <= len(result.artifact.get("candidate_keys", [])),
                critical=True,
            ),
        ),
    ),
)
