"""Jira port."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from agent_pm.integrations.jira.models import JiraUpdate, SprintSnapshot, VelocitySnapshot


@runtime_checkable
class JiraClient(Protocol):
    """What the agent needs from Jira — nothing more.

    Reads are safe to call at any autonomy level. ``apply_update`` is a write
    and must only ever be invoked with a payload that carries an approval.
    """

    async def get_sprint_snapshot(
        self, project_key: str, *, board_id: str | None = None
    ) -> SprintSnapshot:
        """Current sprint with every issue, assignee and blocked flag."""
        ...

    async def get_velocity(
        self, project_key: str, *, sprint_count: int = 6
    ) -> VelocitySnapshot:
        """Points completed per recent sprint."""
        ...

    async def apply_update(self, update: JiraUpdate) -> dict[str, Any]:
        """Execute an approved write. Returns what changed, for the audit row."""
        ...

    async def aclose(self) -> None: ...
