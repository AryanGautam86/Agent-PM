"""Application-side profile for a Supabase auth user."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent_pm.core.enums import AppRole, PodRole
from agent_pm.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from agent_pm.db.types import StrEnumType

if TYPE_CHECKING:
    from agent_pm.models.engagement import Engagement


class User(Base, TimestampMixin):
    """Mirror of ``auth.users``.

    ``id`` is deliberately not generated here — it is the Supabase auth uid, so
    the two stay joinable and a token's ``sub`` maps straight to a row. Rows are
    created on first authenticated request (see ``services/user_service.py``).
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(1024))
    role: Mapped[AppRole] = mapped_column(
        StrEnumType(AppRole), default=AppRole.ENGINEER, nullable=False
    )
    auth_provider: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[EngagementMember]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def display_name(self) -> str:
        return self.full_name or self.email.split("@")[0]


class EngagementMember(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Pod membership. Also the authorisation edge: no row, no access."""

    __tablename__ = "engagement_members"
    __table_args__ = (
        UniqueConstraint("engagement_id", "user_id", name="uq_engagement_members_engagement_user"),
    )

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        # Removing an engagement removes its membership rows.
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        index=True,
    )
    pod_role: Mapped[PodRole] = mapped_column(
        StrEnumType(PodRole), default=PodRole.ENGINEER, nullable=False
    )
    jira_account_id: Mapped[str | None] = mapped_column(String(128))
    github_login: Mapped[str | None] = mapped_column(String(128))
    capacity_hours_per_sprint: Mapped[int | None] = mapped_column(Integer)
    nudges_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship(back_populates="memberships", lazy="joined")
    engagement: Mapped[Engagement] = relationship(back_populates="members")
