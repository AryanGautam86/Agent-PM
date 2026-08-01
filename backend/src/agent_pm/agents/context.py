"""Immutable input to an agent task.

Agent tasks never touch the database. Everything they need is copied into a
``TaskContext`` by the calling service, which is what makes a task unit-testable
with nothing but fixtures — no session, no transaction, no network beyond the
integration ports it is handed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import BaseModel

from agent_pm.core.enums import AutonomyLevel, PodRole
from agent_pm.integrations.registry import IntegrationRegistry


class MemberContext(BaseModel):
    user_id: uuid.UUID | None = None
    display_name: str
    email: str | None = None
    pod_role: PodRole = PodRole.ENGINEER
    jira_account_id: str | None = None
    github_login: str | None = None
    capacity_hours_per_sprint: int | None = None
    nudges_enabled: bool = True


class EngagementContext(BaseModel):
    """Flat projection of an ``Engagement`` row plus its members."""

    id: uuid.UUID
    slug: str
    name: str
    client_name: str | None = None
    timezone: str = "UTC"
    jira_project_key: str | None = None
    jira_board_id: str | None = None
    github_repo: str | None = None
    raid_workbook_url: str | None = None
    channel_target: str | None = None
    autonomy_ceiling: AutonomyLevel = AutonomyLevel.L3_ACT_REVIEW
    members: list[MemberContext] = []

    @property
    def agent_identity(self) -> str:
        return f"agent-pm-{self.slug}"

    def member_by_name(self, name: str) -> MemberContext | None:
        lowered = name.strip().lower()
        return next(
            (m for m in self.members if m.display_name.strip().lower() == lowered), None
        )

    def product_owner(self) -> MemberContext | None:
        return next(
            (m for m in self.members if m.pod_role is PodRole.PRODUCT_OWNER), None
        )


@dataclass(frozen=True, slots=True)
class TaskContext:
    """What a task is given. Read-only by construction."""

    engagement: EngagementContext
    registry: IntegrationRegistry
    for_date: date
    trigger: str = "api"
    triggered_by_user_id: uuid.UUID | None = None

    prior: dict[str, Any] = field(default_factory=dict)
    """State the service loaded on the task's behalf — e.g. ``prior_eod``
    (yesterday's summary) or ``raid_source_refs`` (what the RAID log already
    covers). Keyed by task convention, documented on each task."""

    params: dict[str, Any] = field(default_factory=dict)
    """Per-invocation options, e.g. ``{"force_regenerate": True}``."""

    def param(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)
