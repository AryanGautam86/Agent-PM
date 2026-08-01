"""Action items tracked to closure, with nudges and escalation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from agent_pm.core.clock import utc_now
from agent_pm.core.enums import ActionItemSource, ActionItemStatus
from agent_pm.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from agent_pm.db.types import StrEnumType


class ActionItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Something someone owes the pod.

    "Overdue" is derived from ``due_at`` rather than stored as a status, so a
    missed nudge cycle cannot leave a stale flag behind. ``nudge_count`` and
    ``last_nudged_at`` implement the brief's fatigue cap.
    """

    __tablename__ = "action_items"
    __table_args__ = (
        # The hourly sweep scans open items by due date; this is the index it
        # rides. A standalone due_at index would be redundant, because no query
        # here looks at a due date without also filtering on status.
        Index("ix_action_items_status_due_at", "status", "due_at"),
    )

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", onupdate="CASCADE"),
        index=True,
    )
    owner_label: Mapped[str | None] = mapped_column(String(255))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[ActionItemStatus] = mapped_column(
        StrEnumType(ActionItemStatus),
        default=ActionItemStatus.OPEN,
        nullable=False,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- provenance -------------------------------------------------------
    source: Mapped[ActionItemSource] = mapped_column(
        StrEnumType(ActionItemSource), default=ActionItemSource.MANUAL, nullable=False
    )
    source_ref: Mapped[str | None] = mapped_column(String(255))
    citations: Mapped[list[dict[str, Any]]] = mapped_column(default=list, nullable=False)

    # --- follow-up state --------------------------------------------------
    nudge_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_nudged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nudges_muted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    @property
    def is_open(self) -> bool:
        return self.status in {ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS}

    @property
    def is_overdue(self) -> bool:
        return bool(self.is_open and self.due_at and self.due_at < utc_now())

    def hours_until_due(self, *, now: datetime | None = None) -> float | None:
        if self.due_at is None:
            return None
        return (self.due_at - (now or utc_now())).total_seconds() / 3600
