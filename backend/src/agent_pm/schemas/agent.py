"""Standups, agent runs, and the task catalog."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from agent_pm.core.enums import (
    AutonomyLevel,
    ModelTier,
    RunStatus,
    StandupKind,
    StandupStatus,
)
from agent_pm.schemas.common import ORMModel


class StandupCreate(BaseModel):
    """A standup typed by a person rather than generated."""

    kind: StandupKind = StandupKind.MORNING
    for_date: date | None = Field(
        default=None, description="Defaults to today in the engagement's timezone."
    )
    topic: str = Field(min_length=1, max_length=255)
    summary_markdown: str = Field(min_length=1)


class StandupRead(ORMModel):
    id: uuid.UUID
    engagement_id: uuid.UUID
    kind: StandupKind
    for_date: date
    status: StandupStatus
    topic: str | None = None
    author_user_id: uuid.UUID | None = None
    summary_markdown: str
    per_person: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    highlights: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None
    grounding_ratio: float | None = None
    generated_at: datetime | None = None
    posted_at: datetime | None = None
    error: str | None = None


class StandupGenerateRequest(BaseModel):
    for_date: date | None = Field(
        default=None,
        description="Defaults to today in the engagement's timezone.",
    )
    force_regenerate: bool = Field(
        default=False,
        description="Overwrite an existing post for this date. Without it, a "
        "second call returns the existing row untouched.",
    )
    post_to_channel: bool | None = Field(
        default=None,
        description="Override whether the card is posted. Ignored when the "
        "task's autonomy level does not permit posting.",
    )


class AgentRunRead(ORMModel):
    id: uuid.UUID
    engagement_id: uuid.UUID | None = None
    task_name: str
    trigger: str
    status: RunStatus
    autonomy_level: AutonomyLevel
    model_tier: ModelTier | None = None
    model: str | None = None
    input_digest: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    grounding_ratio: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    started_at: datetime
    finished_at: datetime | None = None
    error_code: str | None = None
    error: str | None = None


class TaskCatalogEntry(BaseModel):
    name: str
    title: str
    description: str
    autonomy: str
    model_tier: str
    requires_citations: bool
    posts_to_channel: bool
    needs_approval: bool
    approval_kind: str


class TaskRunRequest(BaseModel):
    """Manual invocation of any catalog task."""

    for_date: date | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class TaskRunResponse(BaseModel):
    run: AgentRunRead
    skipped: bool = False
    skip_reason: str | None = None
    summary_markdown: str = ""
    approvals_created: int = 0
    posted: bool = False
    notes: list[str] = Field(default_factory=list)
