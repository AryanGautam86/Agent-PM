"""Weekly client status reports and sprint planning packs."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from agent_pm.core.enums import ReportKind, ReportStatus
from agent_pm.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from agent_pm.db.types import StrEnumType


class Report(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A generated document.

    Content lives here as markdown; ``storage_url`` points at the rendered
    artefact once it is published to document storage. Both are kept so the
    narrative stays diffable between weeks even if the file is moved.
    """

    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint(
            "engagement_id",
            "kind",
            "period_start",
            name="uq_reports_engagement_kind_period_start",
        ),
    )

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[ReportKind] = mapped_column(StrEnumType(ReportKind), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        StrEnumType(ReportStatus), default=ReportStatus.DRAFT, nullable=False
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sections: Mapped[dict[str, Any]] = mapped_column(
        default=dict,
        nullable=False,
        doc="Structured facts behind the prose: velocity, scope delta, risks, "
        "decisions. Kept separate so numbers are not re-parsed out of markdown.",
    )
    citations: Mapped[list[dict[str, Any]]] = mapped_column(default=list, nullable=False)

    storage_url: Mapped[str | None] = mapped_column(String(1024))
    model: Mapped[str | None] = mapped_column(String(64))
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", onupdate="CASCADE")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
