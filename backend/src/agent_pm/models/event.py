"""Agent-to-agent event log.

Inbound ``meeting_outcome`` from the Meeting Agent; outbound ``pm_summary``
and ``pm_eod_summary`` for downstream consumers. Persisting every envelope —
including rejected ones — is what makes the consent rule auditable.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from agent_pm.core.enums import EventStatus, EventType
from agent_pm.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from agent_pm.db.types import StrEnumType


class AgentEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_events"
    __table_args__ = (
        # The Meeting Agent may retry; the same external id must not be
        # processed twice into duplicate action items.
        UniqueConstraint("source", "external_id", name="uq_agent_events_source_external_id"),
    )

    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        index=True,
        doc="Null when the envelope named an engagement we do not know.",
    )
    type: Mapped[EventType] = mapped_column(StrEnumType(EventType), nullable=False, index=True)
    contract_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # inbound | outbound

    source: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "meeting-agent"
    external_id: Mapped[str | None] = mapped_column(String(255))
    consented: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    payload: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)

    status: Mapped[EventStatus] = mapped_column(
        StrEnumType(EventStatus), default=EventStatus.RECEIVED, nullable=False, index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
