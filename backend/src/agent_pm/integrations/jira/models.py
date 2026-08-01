"""Jira DTOs.

Deliberately a narrow projection of Jira's response shape: the fields the agent
tasks actually reason over, nothing else. Widening this is a conscious act.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from pydantic import BaseModel, Field

from agent_pm.core.clock import age_in_days
from agent_pm.core.grounding import Citation

UNASSIGNED = "Unassigned"


class JiraIssue(BaseModel):
    key: str
    summary: str
    status: str
    status_category: str  # "todo" | "in_progress" | "done"
    assignee: str | None = None
    assignee_account_id: str | None = None
    story_points: float | None = None
    labels: list[str] = Field(default_factory=list)
    is_blocked: bool = False
    blocked_since: datetime | None = None
    updated_at: datetime | None = None
    url: str | None = None

    @property
    def owner(self) -> str:
        return self.assignee or UNASSIGNED

    @property
    def is_done(self) -> bool:
        return self.status_category == "done"

    @property
    def blocked_age_days(self) -> float | None:
        if not self.is_blocked or self.blocked_since is None:
            return None
        return age_in_days(self.blocked_since)

    def citation(self) -> Citation:
        return Citation(kind="jira", ref=self.key, url=self.url)


class PersonBreakdown(BaseModel):
    """Committed / delivered / pending for one person — the brief's counts."""

    person: str
    committed: int = 0
    delivered: int = 0
    pending: int = 0
    blocked: int = 0
    points_committed: float = 0.0
    points_delivered: float = 0.0
    issue_keys: list[str] = Field(default_factory=list)


class SprintSnapshot(BaseModel):
    """Everything the standup tasks read from Jira in one shot."""

    project_key: str
    sprint_id: str | None = None
    sprint_name: str | None = None
    sprint_start: datetime | None = None
    sprint_end: datetime | None = None
    issues: list[JiraIssue] = Field(default_factory=list)
    fetched_at: datetime | None = None

    # ---- derived views ---------------------------------------------------

    @property
    def blockers(self) -> list[JiraIssue]:
        return sorted(
            (issue for issue in self.issues if issue.is_blocked and not issue.is_done),
            key=lambda issue: issue.blocked_age_days or 0.0,
            reverse=True,
        )

    @property
    def delivered(self) -> list[JiraIssue]:
        return [issue for issue in self.issues if issue.is_done]

    @property
    def pending(self) -> list[JiraIssue]:
        return [issue for issue in self.issues if not issue.is_done]

    def per_person(self) -> list[PersonBreakdown]:
        buckets: dict[str, PersonBreakdown] = defaultdict(
            lambda: PersonBreakdown(person=UNASSIGNED)
        )
        for issue in self.issues:
            bucket = buckets.setdefault(issue.owner, PersonBreakdown(person=issue.owner))
            bucket.committed += 1
            bucket.points_committed += issue.story_points or 0.0
            bucket.issue_keys.append(issue.key)
            if issue.is_done:
                bucket.delivered += 1
                bucket.points_delivered += issue.story_points or 0.0
            else:
                bucket.pending += 1
            if issue.is_blocked and not issue.is_done:
                bucket.blocked += 1
        return sorted(buckets.values(), key=lambda bucket: bucket.person)

    def citations(self) -> list[Citation]:
        """The full evidence set — what the grounding policy validates against."""
        return [issue.citation() for issue in self.issues]

    def totals(self) -> dict[str, float | int | str | None]:
        return {
            "sprint_name": self.sprint_name,
            "issues": len(self.issues),
            "delivered": len(self.delivered),
            "pending": len(self.pending),
            "blocked": len(self.blockers),
            "points_committed": sum(issue.story_points or 0.0 for issue in self.issues),
            "points_delivered": sum(issue.story_points or 0.0 for issue in self.delivered),
        }


class VelocitySnapshot(BaseModel):
    """Historical completion rate — input to sprint planning prep."""

    project_key: str
    sprint_points: list[dict[str, float | str]] = Field(default_factory=list)

    @property
    def average(self) -> float:
        values = [float(entry["points"]) for entry in self.sprint_points if "points" in entry]
        return sum(values) / len(values) if values else 0.0


class JiraUpdate(BaseModel):
    """A proposed write. Serialised into an ``Approval.payload`` verbatim."""

    issue_key: str
    add_comment: str | None = None
    add_labels: list[str] = Field(default_factory=list)
    remove_labels: list[str] = Field(default_factory=list)
    transition_to: str | None = None
