from __future__ import annotations

import uuid
from datetime import time
from typing import Any

from pydantic import BaseModel, Field, field_validator

from agent_pm.core.clock import resolve_zone
from agent_pm.core.enums import AutonomyLevel
from agent_pm.schemas.auth import MemberRead
from agent_pm.schemas.common import ORMModel

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class EngagementBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    client_name: str | None = None
    description: str | None = None

    teams_channel_id: str | None = None
    teams_webhook_url: str | None = None
    jira_project_key: str | None = Field(default=None, max_length=32)
    jira_board_id: str | None = None
    github_repo: str | None = Field(default=None, pattern=r"^[\w.-]+/[\w.-]+$")
    raid_workbook_url: str | None = None

    timezone: str = "UTC"
    morning_post_time: time = time(8, 0)
    eod_post_time: time = time(17, 30)
    weekly_status_weekday: int = Field(default=4, ge=0, le=6)

    autonomy_ceiling: AutonomyLevel = AutonomyLevel.L3_ACT_REVIEW
    task_overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        resolve_zone(value)  # raises ValidationError if unknown
        return value


class EngagementCreate(EngagementBase):
    slug: str = Field(pattern=SLUG_PATTERN, min_length=2, max_length=64)


class EngagementUpdate(BaseModel):
    """Every field optional — PATCH semantics."""

    name: str | None = None
    client_name: str | None = None
    description: str | None = None
    teams_channel_id: str | None = None
    teams_webhook_url: str | None = None
    jira_project_key: str | None = None
    jira_board_id: str | None = None
    github_repo: str | None = None
    raid_workbook_url: str | None = None
    timezone: str | None = None
    morning_post_time: time | None = None
    eod_post_time: time | None = None
    weekly_status_weekday: int | None = Field(default=None, ge=0, le=6)
    autonomy_ceiling: AutonomyLevel | None = None
    task_overrides: dict[str, Any] | None = None
    is_active: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            resolve_zone(value)
        return value


class EngagementRead(ORMModel, EngagementBase):
    id: uuid.UUID
    slug: str
    is_active: bool
    agent_identity: str = ""

    @classmethod
    def from_model(cls, engagement: Any) -> EngagementRead:
        read = cls.model_validate(engagement)
        read.agent_identity = engagement.agent_identity
        return read


class EngagementDetail(EngagementRead):
    members: list[MemberRead] = Field(default_factory=list)


class EngagementSummary(BaseModel):
    """One project's headline numbers, for the dashboard.

    Computed with counting queries rather than by loading rows, so showing
    twenty projects stays cheap.
    """

    id: uuid.UUID
    name: str
    slug: str
    client_name: str | None = None
    agent_identity: str

    open_tasks: int = 0
    overdue_tasks: int = 0
    done_tasks: int = 0
    open_raid: int = 0
    pending_approvals: int = 0
    members: int = 0
    last_standup_on: str | None = None

    @property
    def task_percent(self) -> int:
        total = self.open_tasks + self.done_tasks
        return 0 if total == 0 else round(self.done_tasks / total * 100)
