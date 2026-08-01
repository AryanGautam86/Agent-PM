"""Append-only execution audit for every agent task run.

This is the record that answers "why did the agent say that" — the obligation
the brief placed on Purview. A row is opened before any work happens, so even a
crash leaves evidence. Rows are never updated after they close, and never
deleted.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from agent_pm.core.enums import AutonomyLevel, ModelTier, RunStatus
from agent_pm.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from agent_pm.db.types import StrEnumType


class AgentRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_runs"

    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), index=True
    )
    task_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)  # schedule | api | event
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", onupdate="CASCADE")
    )

    status: Mapped[RunStatus] = mapped_column(
        StrEnumType(RunStatus), default=RunStatus.RUNNING, nullable=False, index=True
    )
    autonomy_level: Mapped[AutonomyLevel] = mapped_column(
        StrEnumType(AutonomyLevel), nullable=False
    )
    model_tier: Mapped[ModelTier | None] = mapped_column(StrEnumType(ModelTier))
    model: Mapped[str | None] = mapped_column(String(64))

    input_digest: Mapped[dict[str, Any]] = mapped_column(
        default=dict,
        nullable=False,
        doc="Summary of the evidence the task ran on — counts and identifiers, "
        "not full payloads, so the audit log stays queryable.",
    )
    output_summary: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    grounding_ratio: Mapped[float | None] = mapped_column(Float)

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
