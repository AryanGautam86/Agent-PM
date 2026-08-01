"""Human-in-the-loop approvals — the gate on every external write."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from agent_pm.core.clock import utc_now
from agent_pm.core.enums import ApprovalKind, ApprovalStatus
from agent_pm.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from agent_pm.db.types import StrEnumType


class Approval(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A proposed change awaiting a human decision.

    ``payload`` is the *exact* change that will be executed on approval. The
    agent cannot substitute a different write between proposal and approval,
    which is what makes "zero unapproved writes" auditable rather than
    aspirational: the approved payload and the executed payload are the same
    object.

    Rows are never deleted. Expiry is an auto-deny, per the brief.
    """

    __tablename__ = "approvals"

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[ApprovalKind] = mapped_column(StrEnumType(ApprovalKind), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        StrEnumType(ApprovalStatus),
        default=ApprovalStatus.PENDING,
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    rationale: Mapped[str | None] = mapped_column(
        Text, doc="Why the agent is proposing this, in the PO's language."
    )
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict, nullable=False)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(default=list, nullable=False)

    # --- request ----------------------------------------------------------
    requested_by_task: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    # --- decision ---------------------------------------------------------
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL", onupdate="CASCADE")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    edited_payload: Mapped[dict[str, Any] | None] = mapped_column(
        doc="Set when the approver changed the proposal before accepting. "
        "Drives the 'approved with minor/no edits' KPI."
    )

    # --- execution --------------------------------------------------------
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_result: Mapped[dict[str, Any] | None] = mapped_column()
    execution_error: Mapped[str | None] = mapped_column(Text)

    @property
    def is_pending(self) -> bool:
        return self.status is ApprovalStatus.PENDING

    @property
    def is_expired(self) -> bool:
        return bool(self.is_pending and self.expires_at and self.expires_at < utc_now())

    @property
    def effective_payload(self) -> dict[str, Any]:
        """What execution should actually apply."""
        return self.edited_payload or self.payload

    @property
    def was_edited(self) -> bool:
        return self.edited_payload is not None
