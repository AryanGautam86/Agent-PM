"""Morning sprint plan and end-of-day summary posts."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from agent_pm.core.enums import StandupKind, StandupStatus
from agent_pm.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from agent_pm.db.types import StrEnumType


class Standup(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One generated standup post.

    The unique constraint on (engagement, kind, date) is load-bearing: a
    scheduler retry, a duplicate Render instance, or a manual re-run must not
    produce a second post for the same morning. Regeneration updates the row.
    """

    __tablename__ = "standups"
    __table_args__ = (
        UniqueConstraint(
            "engagement_id", "kind", "for_date", name="uq_standups_engagement_kind_for_date"
        ),
    )

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[StandupKind] = mapped_column(StrEnumType(StandupKind), nullable=False)
    for_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[StandupStatus] = mapped_column(
        StrEnumType(StandupStatus), default=StandupStatus.DRAFT, nullable=False
    )

    topic: Mapped[str | None] = mapped_column(
        String(255), doc="Headline for a hand-written standup."
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", onupdate="CASCADE"),
        doc="Set when a person wrote this. Null means the agent generated it.",
    )

    summary_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")

    per_person: Mapped[list[dict[str, Any]]] = mapped_column(
        default=list,
        nullable=False,
        doc="[{person, committed, delivered, pending, issue_keys}] — the "
        "committed/delivered/pending counts the brief asks for.",
    )
    blockers: Mapped[list[dict[str, Any]]] = mapped_column(
        default=list,
        nullable=False,
        doc="[{issue_key, summary, assignee, blocked_since, age_days}]",
    )
    highlights: Mapped[list[dict[str, Any]]] = mapped_column(default=list, nullable=False)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(
        default=list,
        nullable=False,
        doc="Evidence backing the narrative — see core/grounding.py.",
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(
        default=dict,
        nullable=False,
        doc="Roll-ups: sprint name, day N of M, totals, velocity signal.",
    )

    # --- provenance -------------------------------------------------------
    model: Mapped[str | None] = mapped_column(String(64))
    grounding_ratio: Mapped[float | None] = mapped_column()
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    post_target: Mapped[str | None] = mapped_column(String(255))
    error: Mapped[str | None] = mapped_column(Text)
