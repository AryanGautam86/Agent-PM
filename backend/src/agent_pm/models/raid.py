"""RAID log entries — risks, assumptions, issues, dependencies."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from agent_pm.core.enums import RaidSource, RaidStatus, RaidType, Severity
from agent_pm.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from agent_pm.db.types import StrEnumType


class RaidItem(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A RAID row.

    The workbook remains the client-visible artefact, so this table is a
    two-way mirror rather than the sole record: ``external_row_ref`` ties a row
    back to its position in the workbook, and ``synced_at`` says when the two
    last agreed. Items created here start with ``external_row_ref = NULL`` and
    acquire one once an approved write lands in the workbook.
    """

    __tablename__ = "raid_items"
    __table_args__ = (
        # The gap scan asks "is this Jira key already in RAID" once per blocker
        # on every run, always scoped to one engagement.
        Index("ix_raid_items_source_ref", "engagement_id", "source_ref"),
    )

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[RaidType] = mapped_column(StrEnumType(RaidType), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    mitigation: Mapped[str | None] = mapped_column(Text)

    status: Mapped[RaidStatus] = mapped_column(
        StrEnumType(RaidStatus), default=RaidStatus.OPEN, nullable=False, index=True
    )
    severity: Mapped[Severity] = mapped_column(
        StrEnumType(Severity), default=Severity.MEDIUM, nullable=False
    )
    probability: Mapped[Severity | None] = mapped_column(StrEnumType(Severity))
    impact: Mapped[Severity | None] = mapped_column(StrEnumType(Severity))

    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", onupdate="CASCADE")
    )
    owner_label: Mapped[str | None] = mapped_column(
        String(255), doc="Free-text owner for people without an app account."
    )
    due_date: Mapped[date | None] = mapped_column(Date)

    # --- provenance -------------------------------------------------------
    source: Mapped[RaidSource] = mapped_column(
        StrEnumType(RaidSource), default=RaidSource.MANUAL, nullable=False
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(255), doc="Jira key, meeting id, or the blocker that promoted into this."
    )
    citations: Mapped[list[dict[str, Any]]] = mapped_column(default=list, nullable=False)

    # --- workbook mirror --------------------------------------------------
    external_row_ref: Mapped[str | None] = mapped_column(String(128))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
