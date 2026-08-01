"""An engagement is one project pod — the unit of tenancy."""

from __future__ import annotations

from datetime import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent_pm.core.enums import AutonomyLevel
from agent_pm.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from agent_pm.db.types import StrEnumType

if TYPE_CHECKING:
    from agent_pm.models.user import EngagementMember


class Engagement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per project.

    The brief called for one agent instance per project. Here that is a row,
    not a deployment: everything engagement-specific (channel binding, Jira
    project, schedule, autonomy ceiling) is configuration on this record. The
    agent identity ``agent-pm-{slug}`` is derived, not stored.
    """

    __tablename__ = "engagements"

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

    # --- integration bindings -------------------------------------------
    teams_channel_id: Mapped[str | None] = mapped_column(String(255))
    teams_webhook_url: Mapped[str | None] = mapped_column(String(1024))
    jira_project_key: Mapped[str | None] = mapped_column(String(32))
    jira_board_id: Mapped[str | None] = mapped_column(String(32))
    github_repo: Mapped[str | None] = mapped_column(String(255))  # "owner/name"
    raid_workbook_url: Mapped[str | None] = mapped_column(String(1024))

    # --- cadence ---------------------------------------------------------
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    morning_post_time: Mapped[time] = mapped_column(
        Time, default=time(8, 0), nullable=False
    )
    eod_post_time: Mapped[time] = mapped_column(Time, default=time(17, 30), nullable=False)
    weekly_status_weekday: Mapped[int] = mapped_column(default=4, nullable=False)  # Friday

    # --- policy ----------------------------------------------------------
    autonomy_ceiling: Mapped[AutonomyLevel] = mapped_column(
        StrEnumType(AutonomyLevel),
        default=AutonomyLevel.L3_ACT_REVIEW,
        nullable=False,
        doc="No task may act above this level for this engagement, whatever "
        "the task declares. Lets a new pod start conservative.",
    )
    task_overrides: Mapped[dict[str, Any]] = mapped_column(
        default=dict,
        nullable=False,
        doc="Per-task switches, e.g. {'eod_summary': {'enabled': false}}.",
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    members: Mapped[list[EngagementMember]] = relationship(
        back_populates="engagement",
        cascade="all, delete-orphan",
    )

    @property
    def agent_identity(self) -> str:
        return f"agent-pm-{self.slug}"

    def task_enabled(self, task_name: str) -> bool:
        override = self.task_overrides.get(task_name, {})
        return bool(override.get("enabled", True))

    def effective_autonomy(self, declared: AutonomyLevel) -> AutonomyLevel:
        """Clamp a task's declared level to this engagement's ceiling."""
        order = list(AutonomyLevel)
        return min(declared, self.autonomy_ceiling, key=order.index)
