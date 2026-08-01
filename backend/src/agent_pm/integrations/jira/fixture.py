"""Deterministic Jira stand-in.

Used whenever Jira credentials are absent, so the whole pipeline — standup
generation, gap scan, approvals — can be exercised offline and in tests. The
data is stable for a given project key and day, which means a test asserting on
"three blockers" keeps passing tomorrow.

Writes are recorded rather than performed; ``applied_updates`` lets a test
assert that an approved write was attempted with the exact approved payload.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from agent_pm.core.clock import utc_now
from agent_pm.integrations.jira.models import (
    JiraIssue,
    JiraUpdate,
    SprintSnapshot,
    VelocitySnapshot,
)

_PEOPLE = ["Priya Nair", "Daniel Okafor", "Mei Lin", "Tomas Vidal"]

# (offset, owner index, status_category, points, blocked, blocked_age_days)
_TEMPLATE: list[tuple[int, int, str, float, bool, int]] = [
    (1, 0, "done", 3, False, 0),
    (2, 0, "in_progress", 5, False, 0),
    (3, 0, "todo", 2, False, 0),
    (4, 1, "done", 8, False, 0),
    (5, 1, "in_progress", 3, True, 4),
    (6, 1, "todo", 5, False, 0),
    (7, 2, "done", 2, False, 0),
    (8, 2, "in_progress", 5, True, 1),
    (9, 2, "todo", 3, False, 0),
    (10, 3, "in_progress", 8, False, 0),
    (11, 3, "todo", 5, True, 3),
    (12, 3, "todo", 2, False, 0),
]

_SUMMARIES = [
    "Add OTP fallback to the login screen",
    "Migrate reporting queries to the read replica",
    "Fix pagination on the audit log",
    "Instrument checkout latency",
    "Upgrade the payments SDK",
    "Backfill missing invoice references",
    "Harden the webhook signature check",
    "Split the settings module",
    "Add retry to the export worker",
    "Cache the pricing lookup",
    "Vendor SSO integration handshake",
    "Tidy the deployment runbook",
]

_STATUS_NAMES = {"done": "Done", "in_progress": "In Progress", "todo": "To Do"}


class FixtureJiraClient:
    """Implements :class:`~agent_pm.integrations.jira.base.JiraClient`."""

    name = "jira-fixture"

    def __init__(self) -> None:
        self.applied_updates: list[JiraUpdate] = []

    async def get_sprint_snapshot(
        self, project_key: str, *, board_id: str | None = None
    ) -> SprintSnapshot:
        now = utc_now()
        prefix = (project_key or "DEMO").upper()
        issues = [
            JiraIssue(
                key=f"{prefix}-{100 + offset}",
                summary=_SUMMARIES[index % len(_SUMMARIES)],
                status=_STATUS_NAMES[category],
                status_category=category,
                assignee=_PEOPLE[owner],
                assignee_account_id=f"acct-{owner}",
                story_points=points,
                labels=["blocked"] if blocked else [],
                is_blocked=blocked,
                blocked_since=now - timedelta(days=blocked_days) if blocked else None,
                updated_at=now - timedelta(hours=offset),
                url=f"https://example.atlassian.net/browse/{prefix}-{100 + offset}",
            )
            for index, (offset, owner, category, points, blocked, blocked_days) in enumerate(
                _TEMPLATE
            )
        ]

        return SprintSnapshot(
            project_key=prefix,
            sprint_id="fixture-sprint-1",
            sprint_name=f"{prefix} Sprint 14",
            sprint_start=now - timedelta(days=6),
            sprint_end=now + timedelta(days=8),
            issues=issues,
            fetched_at=now,
        )

    async def get_velocity(
        self, project_key: str, *, sprint_count: int = 6
    ) -> VelocitySnapshot:
        return VelocitySnapshot(
            project_key=(project_key or "DEMO").upper(),
            sprint_points=[
                {"sprint": f"Sprint {number}", "points": float(points)}
                for number, points in zip(
                    range(14 - sprint_count, 14),
                    [28, 31, 26, 34, 29, 30][:sprint_count],
                    strict=False,
                )
            ],
        )

    async def apply_update(self, update: JiraUpdate) -> dict[str, Any]:
        self.applied_updates.append(update)
        return {
            "issue_key": update.issue_key,
            "operations": [
                name
                for name, present in (
                    ("comment", bool(update.add_comment)),
                    ("labels", bool(update.add_labels or update.remove_labels)),
                    ("transition", bool(update.transition_to)),
                )
                if present
            ],
            "simulated": True,
        }

    async def aclose(self) -> None:
        return None
