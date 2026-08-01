"""Grounding policy — the anti-hallucination gate.

The brief's hardest rule: *always cite the Jira ticket, commit, message, or
transcript timestamp that grounds a claim*, and *never claim work is done
without evidence*. This module turns that rule into something enforceable.

Every agent task returns claims alongside citations. Before anything is posted
or written, :meth:`GroundingPolicy.validate` checks that enough claims are
backed by a citation that actually appeared in the evidence the task was given
— a citation the model invented is worse than no citation at all.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from agent_pm.core.errors import GroundingError

# Jira keys: ABC-123. Commits: 7-40 hex chars. Message/transcript refs are
# opaque ids the integration layer supplies.
JIRA_KEY_PATTERN = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
COMMIT_SHA_PATTERN = re.compile(r"\b[0-9a-f]{7,40}\b")
TIMESTAMP_PATTERN = re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b")


@dataclass(frozen=True, slots=True)
class Citation:
    """A pointer to the evidence behind a claim."""

    kind: str  # "jira" | "commit" | "message" | "transcript"
    ref: str  # "ACME-412", a SHA, a message id, "00:14:22"
    url: str | None = None

    def normalised(self) -> str:
        return f"{self.kind}:{self.ref}".lower()


@dataclass(frozen=True, slots=True)
class Claim:
    """One assertion the agent wants to publish."""

    text: str
    citations: tuple[Citation, ...] = ()

    @property
    def is_grounded(self) -> bool:
        return bool(self.citations)


@dataclass(slots=True)
class GroundingReport:
    total_claims: int
    grounded_claims: int
    unsupported: list[str] = field(default_factory=list)
    fabricated: list[str] = field(default_factory=list)

    @property
    def ratio(self) -> float:
        if self.total_claims == 0:
            return 1.0
        return self.grounded_claims / self.total_claims

    @property
    def passed(self) -> bool:
        return not self.fabricated and not self.unsupported


class GroundingPolicy:
    """Validates claims against the evidence a task was actually given.

    Args:
        min_citation_ratio: fraction of claims that must carry a citation.
        allow_unknown_refs: when True, a citation that is not in the evidence
            set is a warning rather than a failure. Only appropriate for tasks
            whose evidence set cannot be fully enumerated up front.
    """

    def __init__(
        self,
        min_citation_ratio: float = 0.9,
        *,
        allow_unknown_refs: bool = False,
    ) -> None:
        if not 0.0 <= min_citation_ratio <= 1.0:
            raise ValueError("min_citation_ratio must be between 0 and 1")
        self.min_citation_ratio = min_citation_ratio
        self.allow_unknown_refs = allow_unknown_refs

    def inspect(self, claims: Sequence[Claim], evidence: Iterable[Citation]) -> GroundingReport:
        known = {citation.normalised() for citation in evidence}
        report = GroundingReport(total_claims=len(claims), grounded_claims=0)

        for claim in claims:
            if not claim.is_grounded:
                report.unsupported.append(claim.text)
                continue

            invented = [
                citation.ref
                for citation in claim.citations
                if citation.normalised() not in known
            ]
            if invented and not self.allow_unknown_refs:
                report.fabricated.append(f"{claim.text} → {', '.join(invented)}")
                continue

            report.grounded_claims += 1

        return report

    def validate(self, claims: Sequence[Claim], evidence: Iterable[Citation]) -> GroundingReport:
        """Raise :class:`GroundingError` unless the output is well grounded.

        A fabricated citation always fails, regardless of ratio: one invented
        Jira key destroys trust in the whole post.
        """
        report = self.inspect(claims, evidence)

        if report.fabricated:
            raise GroundingError(
                "Agent cited evidence that was not in its inputs",
                details={"fabricated": report.fabricated, "ratio": report.ratio},
            )

        if report.ratio < self.min_citation_ratio:
            raise GroundingError(
                f"Only {report.ratio:.0%} of claims are cited; "
                f"policy requires {self.min_citation_ratio:.0%}",
                details={"unsupported": report.unsupported, "ratio": report.ratio},
            )

        return report


def extract_refs(text: str) -> list[Citation]:
    """Best-effort scan of free text for evidence references.

    Used to catch claims where the model mentioned a ticket inline instead of
    populating the citations field — the reference is real, the structure is
    just wrong, so we recover it rather than failing the whole post.
    """
    found: list[Citation] = []
    seen: set[str] = set()

    for match in JIRA_KEY_PATTERN.finditer(text):
        citation = Citation(kind="jira", ref=match.group())
        if citation.normalised() not in seen:
            seen.add(citation.normalised())
            found.append(citation)

    for match in COMMIT_SHA_PATTERN.finditer(text):
        # Skip anything already claimed as part of a Jira key.
        if JIRA_KEY_PATTERN.search(match.group()):
            continue
        citation = Citation(kind="commit", ref=match.group())
        if citation.normalised() not in seen:
            seen.add(citation.normalised())
            found.append(citation)

    return found
