"""Jira Cloud adapter (REST API v3, basic auth with an API token)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from dateutil import parser as date_parser

from agent_pm.core.clock import utc_now
from agent_pm.core.config import Settings
from agent_pm.core.errors import IntegrationError
from agent_pm.core.logging import get_logger
from agent_pm.integrations.base import HttpIntegration
from agent_pm.integrations.jira.models import (
    JiraIssue,
    JiraUpdate,
    SprintSnapshot,
    VelocitySnapshot,
)

logger = get_logger(__name__)

# Jira has no first-class "blocked" concept, so every deployment expresses it
# differently. These are the three conventions we recognise; an engagement that
# uses another one needs this list extended rather than the logic rewritten.
BLOCKED_LABELS = frozenset({"blocked", "is-blocked", "impediment"})
BLOCKED_STATUSES = frozenset({"blocked", "impeded", "on hold"})

SEARCH_FIELDS = [
    "summary",
    "status",
    "assignee",
    "labels",
    "updated",
    "statuscategorychangedate",
    "customfield_10016",  # story points on most Jira Cloud sites
]


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return date_parser.isoparse(str(value))
    except (ValueError, TypeError):
        return None


class JiraCloudClient(HttpIntegration):
    name = "jira"

    def __init__(self, settings: Settings) -> None:
        if not settings.jira_configured:
            raise IntegrationError("jira", "Jira credentials are not configured")
        super().__init__(
            base_url=settings.jira_base_url.rstrip("/"),
            auth=(settings.jira_email, settings.jira_api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        self._site = settings.jira_base_url.rstrip("/")

    # ---- reads -----------------------------------------------------------

    async def get_sprint_snapshot(
        self, project_key: str, *, board_id: str | None = None
    ) -> SprintSnapshot:
        jql = f'project = "{project_key}" AND sprint in openSprints() ORDER BY assignee'
        payload = await self.post(
            "/rest/api/3/search/jql",
            json={"jql": jql, "maxResults": 200, "fields": SEARCH_FIELDS},
        )
        issues = [self._to_issue(raw) for raw in (payload or {}).get("issues", [])]

        sprint = await self._active_sprint(board_id) if board_id else None
        return SprintSnapshot(
            project_key=project_key,
            sprint_id=str(sprint["id"]) if sprint else None,
            sprint_name=sprint.get("name") if sprint else None,
            sprint_start=_parse_datetime(sprint.get("startDate")) if sprint else None,
            sprint_end=_parse_datetime(sprint.get("endDate")) if sprint else None,
            issues=issues,
            fetched_at=utc_now(),
        )

    async def get_velocity(
        self, project_key: str, *, sprint_count: int = 6
    ) -> VelocitySnapshot:
        """Approximated from recently closed issues.

        The Agile velocity endpoint needs a board id and greedy permissions;
        this is close enough for planning prep and works on any project.
        """
        jql = (
            f'project = "{project_key}" AND statusCategory = Done '
            f"AND resolutiondate >= -{sprint_count * 14}d ORDER BY resolutiondate DESC"
        )
        payload = await self.post(
            "/rest/api/3/search/jql",
            json={"jql": jql, "maxResults": 200, "fields": SEARCH_FIELDS},
        )
        points = sum(
            float(raw.get("fields", {}).get("customfield_10016") or 0)
            for raw in (payload or {}).get("issues", [])
        )
        periods = max(sprint_count, 1)
        return VelocitySnapshot(
            project_key=project_key,
            sprint_points=[
                {"sprint": f"last-{periods}-sprints-average", "points": points / periods}
            ],
        )

    # ---- writes ----------------------------------------------------------

    async def apply_update(self, update: JiraUpdate) -> dict[str, Any]:
        applied: dict[str, Any] = {"issue_key": update.issue_key, "operations": []}

        if update.add_comment:
            await self.post(
                f"/rest/api/3/issue/{update.issue_key}/comment",
                json={
                    "body": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": update.add_comment}],
                            }
                        ],
                    }
                },
            )
            applied["operations"].append("comment")

        if update.add_labels or update.remove_labels:
            await self.request(
                "PUT",
                f"/rest/api/3/issue/{update.issue_key}",
                json={
                    "update": {
                        "labels": [
                            *({"add": label} for label in update.add_labels),
                            *({"remove": label} for label in update.remove_labels),
                        ]
                    }
                },
            )
            applied["operations"].append("labels")

        if update.transition_to:
            transitions = await self.get(f"/rest/api/3/issue/{update.issue_key}/transitions")
            match = next(
                (
                    transition
                    for transition in (transitions or {}).get("transitions", [])
                    if transition.get("name", "").lower() == update.transition_to.lower()
                ),
                None,
            )
            if match is None:
                raise IntegrationError(
                    "jira",
                    f"No transition named {update.transition_to!r} on {update.issue_key}",
                )
            await self.post(
                f"/rest/api/3/issue/{update.issue_key}/transitions",
                json={"transition": {"id": match["id"]}},
            )
            applied["operations"].append("transition")

        logger.info("jira_update_applied", extra=applied)
        return applied

    # ---- internals -------------------------------------------------------

    async def _active_sprint(self, board_id: str) -> dict[str, Any] | None:
        payload = await self.get(
            f"/rest/agile/1.0/board/{board_id}/sprint", params={"state": "active"}
        )
        values = (payload or {}).get("values", [])
        return values[0] if values else None

    def _to_issue(self, raw: dict[str, Any]) -> JiraIssue:
        fields = raw.get("fields", {})
        status = fields.get("status") or {}
        category = (status.get("statusCategory") or {}).get("key", "new")
        labels = [str(label) for label in fields.get("labels", [])]
        status_name = str(status.get("name", ""))

        blocked = bool(
            {label.lower() for label in labels} & BLOCKED_LABELS
            or status_name.lower() in BLOCKED_STATUSES
        )
        assignee = fields.get("assignee") or {}

        return JiraIssue(
            key=raw["key"],
            summary=str(fields.get("summary", "")),
            status=status_name,
            status_category={"done": "done", "indeterminate": "in_progress"}.get(
                category, "todo"
            ),
            assignee=assignee.get("displayName"),
            assignee_account_id=assignee.get("accountId"),
            story_points=fields.get("customfield_10016"),
            labels=labels,
            is_blocked=blocked,
            # Best available proxy: when the issue last changed status category.
            blocked_since=_parse_datetime(fields.get("statuscategorychangedate"))
            if blocked
            else None,
            updated_at=_parse_datetime(fields.get("updated")),
            url=f"{self._site}/browse/{raw['key']}",
        )
