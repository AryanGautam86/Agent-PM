from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from agent_pm.core.enums import RaidSource, RaidStatus, RaidType, Severity
from agent_pm.schemas.common import ORMModel


class RaidItemBase(BaseModel):
    type: RaidType
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    mitigation: str | None = None
    severity: Severity = Severity.MEDIUM
    probability: Severity | None = None
    impact: Severity | None = None
    owner_user_id: uuid.UUID | None = None
    owner_label: str | None = None
    due_date: date | None = None


class RaidItemCreate(RaidItemBase):
    source: RaidSource = RaidSource.MANUAL
    source_ref: str | None = None


class RaidItemUpdate(BaseModel):
    type: RaidType | None = None
    title: str | None = None
    description: str | None = None
    mitigation: str | None = None
    status: RaidStatus | None = None
    severity: Severity | None = None
    probability: Severity | None = None
    impact: Severity | None = None
    owner_user_id: uuid.UUID | None = None
    owner_label: str | None = None
    due_date: date | None = None


class RaidItemRead(ORMModel, RaidItemBase):
    id: uuid.UUID
    engagement_id: uuid.UUID
    status: RaidStatus
    source: RaidSource
    source_ref: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    external_row_ref: str | None = None
    synced_at: datetime | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RaidGapScanResponse(BaseModel):
    """Result of a gap scan. Nothing here has been written anywhere."""

    checked_blockers: int
    gaps_found: int
    approvals_created: int
    gap_keys: list[str] = Field(default_factory=list)
    summary_markdown: str = ""
