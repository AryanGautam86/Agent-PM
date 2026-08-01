"""Shared machinery for the two daily standup tasks.

Morning and EOD differ in what they emphasise, not in how they read Jira or
how they render a card. Everything common lives here so the two tasks stay
short enough to read in one screen.
"""

from __future__ import annotations

from typing import Any

from agent_pm.agents.base import AgentTask
from agent_pm.agents.context import TaskContext
from agent_pm.core.enums import AutonomyLevel, ModelTier
from agent_pm.core.grounding import Citation
from agent_pm.integrations.github.base import RepoActivity
from agent_pm.integrations.jira.models import JiraIssue, PersonBreakdown, SprintSnapshot
from agent_pm.integrations.teams.base import CardSection, ChannelCard


class StandupTaskBase(AgentTask):
    """Common behaviour: L3 autonomy, structured model, posts to the channel."""

    autonomy = AutonomyLevel.L3_ACT_REVIEW
    model_tier = ModelTier.STRUCTURED
    requires_citations = True
    posts_to_channel = True

    # ---- evidence rendering ---------------------------------------------

    @staticmethod
    def issue_line(issue: JiraIssue) -> str:
        parts = [f"{issue.key} — {issue.summary}", f"owner: {issue.owner}"]
        parts.append(f"status: {issue.status}")
        if issue.story_points:
            parts.append(f"points: {issue.story_points:g}")
        if issue.is_blocked:
            age = issue.blocked_age_days
            parts.append(f"BLOCKED{f' for {age:.0f}d' if age else ''}")
        return " | ".join(parts)

    @staticmethod
    def person_line(breakdown: PersonBreakdown) -> str:
        return (
            f"{breakdown.person} — committed {breakdown.committed}, "
            f"delivered {breakdown.delivered}, pending {breakdown.pending}, "
            f"blocked {breakdown.blocked} "
            f"({', '.join(breakdown.issue_keys)})"
        )

    @staticmethod
    def commit_lines(activity: RepoActivity | None) -> list[str]:
        if activity is None:
            return []
        lines = [
            f"commit {commit.short_sha} — {commit.title} (by {commit.author or 'unknown'})"
            for commit in activity.commits
        ]
        lines += [
            f"PR #{pr.number} {pr.state} — {pr.title}"
            for pr in activity.pull_requests
        ]
        return lines

    def snapshot_evidence(self, snapshot: SprintSnapshot) -> list[str]:
        lines: list[str] = []
        if snapshot.sprint_name:
            totals = snapshot.totals()
            lines.append(
                f"Sprint {snapshot.sprint_name}: {totals['issues']} issues, "
                f"{totals['delivered']} done, {totals['pending']} pending, "
                f"{totals['blocked']} blocked"
            )
        lines += [self.person_line(person) for person in snapshot.per_person()]
        lines += [self.issue_line(issue) for issue in snapshot.issues]
        return lines

    # ---- artifact --------------------------------------------------------

    @staticmethod
    def build_artifact(
        snapshot: SprintSnapshot, activity: RepoActivity | None = None
    ) -> dict[str, Any]:
        """The structured half of a standup row.

        Counts are computed here, never taken from the model. The model writes
        prose about numbers; it does not produce them.
        """
        return {
            "per_person": [person.model_dump() for person in snapshot.per_person()],
            "blockers": [
                {
                    "issue_key": issue.key,
                    "summary": issue.summary,
                    "assignee": issue.owner,
                    "status": issue.status,
                    "age_days": round(issue.blocked_age_days or 0.0, 1),
                    "url": issue.url,
                }
                for issue in snapshot.blockers
            ],
            "highlights": [
                {"sha": commit.short_sha, "title": commit.title, "author": commit.author}
                for commit in (activity.commits if activity else [])
            ],
            "metrics": snapshot.totals(),
        }

    # ---- card ------------------------------------------------------------

    @staticmethod
    def build_card(
        *,
        title: str,
        subtitle: str | None,
        summary_markdown: str,
        snapshot: SprintSnapshot,
    ) -> ChannelCard:
        sections = [CardSection(body_markdown=summary_markdown)]

        people = snapshot.per_person()
        if people:
            sections.append(
                CardSection(
                    heading="Committed / delivered / pending",
                    facts={
                        person.person: (
                            f"{person.committed} / {person.delivered} / {person.pending}"
                            + (f"  ({person.blocked} blocked)" if person.blocked else "")
                        )
                        for person in people
                    },
                )
            )

        blockers = snapshot.blockers
        sections.append(
            CardSection(
                heading=f"Blockers ({len(blockers)})",
                body_markdown="\n".join(
                    f"- **{issue.key}** {issue.summary} — {issue.owner}"
                    + (
                        f" _(blocked {issue.blocked_age_days:.0f}d)_"
                        if issue.blocked_age_days
                        else ""
                    )
                    for issue in blockers
                )
                or "_None._",
            )
        )

        return ChannelCard(
            title=title,
            subtitle=subtitle,
            sections=sections,
            accent="attention" if blockers else "good",
        )

    # ---- gathering -------------------------------------------------------

    async def fetch_snapshot(self, ctx: TaskContext) -> SprintSnapshot:
        return await ctx.registry.jira.get_sprint_snapshot(
            ctx.engagement.jira_project_key or ctx.engagement.slug.upper(),
            board_id=ctx.engagement.jira_board_id,
        )

    @staticmethod
    def collect_citations(
        snapshot: SprintSnapshot, activity: RepoActivity | None = None
    ) -> list[Citation]:
        citations = snapshot.citations()
        if activity is not None:
            citations += activity.citations()
        return citations
