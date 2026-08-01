from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from agent_pm.core.enums import ReportKind, ReportStatus
from agent_pm.schemas.common import ORMModel


class ReportRead(ORMModel):
    id: uuid.UUID
    engagement_id: uuid.UUID
    kind: ReportKind
    status: ReportStatus
    period_start: date
    period_end: date
    title: str
    content_markdown: str
    sections: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    storage_url: str | None = None
    model: str | None = None
    approved_by_user_id: uuid.UUID | None = None
    approved_at: datetime | None = None
    sent_at: datetime | None = None
    created_at: datetime


class ReportGenerateRequest(BaseModel):
    period_end: date | None = Field(
        default=None, description="Defaults to today in the engagement's timezone."
    )
    force_regenerate: bool = False


class ReportUpdate(BaseModel):
    """Editing before sending is expected — the lead owns the final wording."""

    title: str | None = None
    content_markdown: str | None = None
    status: ReportStatus | None = None
