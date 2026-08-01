"""GitHub port — the engineering signal in the EOD summary."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from agent_pm.core.grounding import Citation


class CommitSummary(BaseModel):
    sha: str
    message: str
    author: str | None = None
    committed_at: datetime | None = None
    url: str | None = None

    @property
    def short_sha(self) -> str:
        return self.sha[:7]

    @property
    def title(self) -> str:
        return self.message.splitlines()[0] if self.message else ""

    def citation(self) -> Citation:
        return Citation(kind="commit", ref=self.short_sha, url=self.url)


class PullRequestSummary(BaseModel):
    number: int
    title: str
    state: str  # open | merged | closed
    author: str | None = None
    merged_at: datetime | None = None
    url: str | None = None
    linked_issue_keys: list[str] = Field(default_factory=list)

    def citation(self) -> Citation:
        return Citation(kind="commit", ref=f"pr-{self.number}", url=self.url)


class RepoActivity(BaseModel):
    repo: str
    since: datetime | None = None
    commits: list[CommitSummary] = Field(default_factory=list)
    pull_requests: list[PullRequestSummary] = Field(default_factory=list)

    @property
    def merged_pull_requests(self) -> list[PullRequestSummary]:
        return [pr for pr in self.pull_requests if pr.state == "merged"]

    def citations(self) -> list[Citation]:
        return [commit.citation() for commit in self.commits] + [
            pr.citation() for pr in self.pull_requests
        ]


@runtime_checkable
class GitHubClient(Protocol):
    async def get_activity(self, repo: str, *, since: datetime) -> RepoActivity:
        """Commits and pull requests touching ``repo`` since a timestamp."""
        ...

    async def aclose(self) -> None: ...
