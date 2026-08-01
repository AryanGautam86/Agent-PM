"""The anti-hallucination gate.

These are the most load-bearing tests in the suite: if grounding stops
rejecting fabricated evidence, the agent can quietly start inventing ticket
numbers in client-visible posts.
"""

from __future__ import annotations

import pytest

from agent_pm.core.errors import GroundingError
from agent_pm.core.grounding import Citation, Claim, GroundingPolicy, extract_refs

EVIDENCE = [
    Citation(kind="jira", ref="DEMO-101"),
    Citation(kind="jira", ref="DEMO-102"),
    Citation(kind="commit", ref="a1b2c3d"),
]


def test_fully_cited_output_passes() -> None:
    claims = [
        Claim("DEMO-101 is done.", (Citation("jira", "DEMO-101"),)),
        Claim("DEMO-102 is blocked.", (Citation("jira", "DEMO-102"),)),
    ]
    report = GroundingPolicy(0.9).validate(claims, EVIDENCE)

    assert report.passed
    assert report.ratio == 1.0


def test_fabricated_citation_always_fails() -> None:
    """Even one invented reference fails, regardless of how good the ratio is."""
    claims = [
        Claim("DEMO-101 is done.", (Citation("jira", "DEMO-101"),)),
        Claim("DEMO-102 is done.", (Citation("jira", "DEMO-102"),)),
        # DEMO-999 was never in the evidence.
        Claim("DEMO-999 shipped.", (Citation("jira", "DEMO-999"),)),
    ]

    with pytest.raises(GroundingError) as exc:
        GroundingPolicy(0.5).validate(claims, EVIDENCE)

    assert "DEMO-999" in str(exc.value.details["fabricated"])


def test_uncited_claims_fail_below_the_threshold() -> None:
    claims = [
        Claim("DEMO-101 is done.", (Citation("jira", "DEMO-101"),)),
        Claim("The team feels good about the sprint."),
        Claim("We will probably finish on time."),
    ]

    with pytest.raises(GroundingError) as exc:
        GroundingPolicy(0.9).validate(claims, EVIDENCE)

    assert len(exc.value.details["unsupported"]) == 2


def test_threshold_allows_some_uncited_commentary() -> None:
    claims = [
        Claim("DEMO-101 is done.", (Citation("jira", "DEMO-101"),)),
        Claim("DEMO-102 is blocked.", (Citation("jira", "DEMO-102"),)),
        Claim("a1b2c3d landed.", (Citation("commit", "a1b2c3d"),)),
        Claim("Overall the sprint is on track."),
    ]
    report = GroundingPolicy(0.75).validate(claims, EVIDENCE)

    assert report.ratio == 0.75


def test_empty_output_is_vacuously_grounded() -> None:
    report = GroundingPolicy(0.9).validate([], EVIDENCE)
    assert report.ratio == 1.0
    assert report.passed


def test_allow_unknown_refs_relaxes_only_the_fabrication_rule() -> None:
    claims = [Claim("DEMO-999 shipped.", (Citation("jira", "DEMO-999"),))]
    report = GroundingPolicy(0.9, allow_unknown_refs=True).validate(claims, EVIDENCE)
    assert report.ratio == 1.0


def test_extract_refs_recovers_inline_mentions() -> None:
    found = extract_refs("Blocked on DEMO-105 and fixed in a1b2c3d4.")
    refs = {citation.ref for citation in found}
    assert "DEMO-105" in refs
    assert "a1b2c3d4" in refs


@pytest.mark.parametrize("ratio", [-0.1, 1.5])
def test_invalid_threshold_is_rejected(ratio: float) -> None:
    with pytest.raises(ValueError):
        GroundingPolicy(ratio)
