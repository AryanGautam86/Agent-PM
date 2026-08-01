"""GitHub REST adapter."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from dateutil import parser as date_parser

from agent_pm.core.config import Settings
from agent_pm.core.errors import IntegrationError
from agent_pm.integrations.base import HttpIntegration
from agent_pm.integrations.github.base import CommitSummary, PullRequestSummary, RepoActivity

JIRA_KEY_IN_TEXT = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return date_parser.isoparse(str(value))
    except (ValueError, TypeError):
        return None


class GitHubRestClient(HttpIntegration):
    name = "github"

    def __init__(self, settings: Settings) -> None:
        if not settings.github_configured:
            raise IntegrationError("github", "GITHUB_TOKEN is not configured")
        super().__init__(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    async def get_activity(self, repo: str, *, since: datetime) -> RepoActivity:
        commits_raw = await self.get(
            f"/repos/{repo}/commits",
            params={"since": since.isoformat(), "per_page": 100},
        )
        commits = [
            CommitSummary(
                sha=raw["sha"],
                message=raw.get("commit", {}).get("message", ""),
                author=(raw.get("author") or {}).get("login")
                or raw.get("commit", {}).get("author", {}).get("name"),
                committed_at=_parse(raw.get("commit", {}).get("author", {}).get("date")),
                url=raw.get("html_url"),
            )
            for raw in (commits_raw or [])
        ]

        # The pulls endpoint has no "since" filter; fetch recently updated and
        # trim locally.
        pulls_raw = await self.get(
            f"/repos/{repo}/pulls",
            params={"state": "all", "sort": "updated", "direction": "desc", "per_page": 50},
        )
        pull_requests: list[PullRequestSummary] = []
        for raw in pulls_raw or []:
            updated = _parse(raw.get("updated_at"))
            if updated and updated < since:
                break
            merged_at = _parse(raw.get("merged_at"))
            title = raw.get("title", "")
            branch = raw.get("head", {}).get("ref", "")
            pull_requests.append(
                PullRequestSummary(
                    number=raw["number"],
                    title=title,
                    state="merged" if merged_at else raw.get("state", "open"),
                    author=(raw.get("user") or {}).get("login"),
                    merged_at=merged_at,
                    url=raw.get("html_url"),
                    # Jira keys turn up in the title or the branch name; either
                    # is enough to link a pull request to a ticket.
                    linked_issue_keys=sorted(
                        set(JIRA_KEY_IN_TEXT.findall(f"{title} {branch}"))
                    ),
                )
            )

        return RepoActivity(
            repo=repo, since=since, commits=commits, pull_requests=pull_requests
        )
