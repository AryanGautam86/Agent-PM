from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agent_pm.core.enums import ActionItemSource, ActionItemStatus
from agent_pm.schemas.common import ORMModel


class ActionItemBase(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    owner_user_id: uuid.UUID | None = None
    owner_label: str | None = None
    due_at: datetime | None = None


class ActionItemCreate(ActionItemBase):
    source: ActionItemSource = ActionItemSource.MANUAL
    source_ref: str | None = None


class ActionItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    owner_user_id: uuid.UUID | None = None
    owner_label: str | None = None
    due_at: datetime | None = None
    status: ActionItemStatus | None = None
    nudges_muted: bool | None = None


class ActionItemRead(ORMModel, ActionItemBase):
    id: uuid.UUID
    engagement_id: uuid.UUID
    status: ActionItemStatus
    source: ActionItemSource
    source_ref: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    nudge_count: int
    last_nudged_at: datetime | None = None
    escalated_at: datetime | None = None
    nudges_muted: bool
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    # Derived — the UI should not recompute "overdue" from a timestamp.
    is_overdue: bool = False


class NudgeSweepResponse(BaseModel):
    nudged: int
    escalated: int
    suppressed_by_cap: int
    detail: list[str] = Field(default_factory=list)
