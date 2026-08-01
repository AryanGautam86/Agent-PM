"""Deterministic GitHub stand-in."""

from __future__ import annotations

from datetime import datetime, timedelta

from agent_pm.core.clock import utc_now
from agent_pm.integrations.github.base import CommitSummary, PullRequestSummary, RepoActivity

_COMMITS = [
    ("a1b2c3d4e5f6a7b8", "DEMO-105 add OTP fallback to login", "priya"),
    ("b2c3d4e5f6a7b809", "DEMO-107 fix audit log pagination", "mei"),
    ("c3d4e5f6a7b80912", "chore: bump payments sdk", "daniel"),
]


class FixtureGitHubClient:
    """Implements :class:`~agent_pm.integrations.github.base.GitHubClient`."""

    name = "github-fixture"

    async def get_activity(self, repo: str, *, since: datetime) -> RepoActivity:
        now = utc_now()
        return RepoActivity(
            repo=repo or "example/demo",
            since=since,
            commits=[
                CommitSummary(
                    sha=sha,
                    message=message,
                    author=author,
                    committed_at=now - timedelta(hours=index + 1),
                    url=f"https://github.com/{repo or 'example/demo'}/commit/{sha}",
                )
                for index, (sha, message, author) in enumerate(_COMMITS)
            ],
            pull_requests=[
                PullRequestSummary(
                    number=412,
                    title="DEMO-105 OTP fallback",
                    state="merged",
                    author="priya",
                    merged_at=now - timedelta(hours=2),
                    url=f"https://github.com/{repo or 'example/demo'}/pull/412",
                    linked_issue_keys=["DEMO-105"],
                )
            ],
        )

    async def aclose(self) -> None:
        return None
