"""Initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
TS = sa.DateTime(timezone=True)


def _timestamps() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    # ---------------------------------------------------------------- users
    op.create_table(
        "users",
        sa.Column("id", UUID, nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("full_name", sa.String(255)),
        sa.Column("avatar_url", sa.String(1024)),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("auth_provider", sa.String(32)),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("last_seen_at", TS),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    # unique=True + index=True on the model is one unique index, not an index
    # plus a separate constraint.
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ---------------------------------------------------------- engagements
    op.create_table(
        "engagements",
        sa.Column("id", UUID, nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("client_name", sa.String(255)),
        sa.Column("description", sa.Text),
        sa.Column("teams_channel_id", sa.String(255)),
        sa.Column("teams_webhook_url", sa.String(1024)),
        sa.Column("jira_project_key", sa.String(32)),
        sa.Column("jira_board_id", sa.String(32)),
        sa.Column("github_repo", sa.String(255)),
        sa.Column("raid_workbook_url", sa.String(1024)),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("morning_post_time", sa.Time, nullable=False),
        sa.Column("eod_post_time", sa.Time, nullable=False),
        sa.Column("weekly_status_weekday", sa.Integer, nullable=False),
        sa.Column("autonomy_ceiling", sa.String(32), nullable=False),
        sa.Column("task_overrides", JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_engagements"),
    )
    op.create_index("ix_engagements_slug", "engagements", ["slug"], unique=True)

    # -------------------------------------------------- engagement_members
    op.create_table(
        "engagement_members",
        sa.Column("id", UUID, nullable=False),
        sa.Column("engagement_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("pod_role", sa.String(32), nullable=False),
        sa.Column("jira_account_id", sa.String(128)),
        sa.Column("github_login", sa.String(128)),
        sa.Column("capacity_hours_per_sprint", sa.Integer),
        sa.Column("nudges_enabled", sa.Boolean, nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_engagement_members"),
        sa.ForeignKeyConstraint(
            ["engagement_id"],
            ["engagements.id"],
            name="fk_engagement_members_engagement_id_engagements",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_engagement_members_user_id_users",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        sa.UniqueConstraint(
            "engagement_id", "user_id", name="uq_engagement_members_engagement_user"
        ),
    )
    op.create_index("ix_engagement_members_engagement_id", "engagement_members", ["engagement_id"])
    op.create_index("ix_engagement_members_user_id", "engagement_members", ["user_id"])

    # ----------------------------------------------------------- agent_runs
    op.create_table(
        "agent_runs",
        sa.Column("id", UUID, nullable=False),
        sa.Column("engagement_id", UUID),
        sa.Column("task_name", sa.String(128), nullable=False),
        sa.Column("trigger", sa.String(32), nullable=False),
        sa.Column("triggered_by_user_id", UUID),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("autonomy_level", sa.String(32), nullable=False),
        sa.Column("model_tier", sa.String(32)),
        sa.Column("model", sa.String(64)),
        sa.Column("input_digest", JSONB, nullable=False),
        sa.Column("output_summary", JSONB, nullable=False),
        sa.Column("grounding_ratio", sa.Float),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("started_at", TS, nullable=False),
        sa.Column("finished_at", TS),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error", sa.Text),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
        sa.ForeignKeyConstraint(
            ["engagement_id"],
            ["engagements.id"],
            name="fk_agent_runs_engagement_id_engagements",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["triggered_by_user_id"],
            ["users.id"],
            name="fk_agent_runs_triggered_by_user_id_users",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
    )
    op.create_index("ix_agent_runs_engagement_id", "agent_runs", ["engagement_id"])
    op.create_index("ix_agent_runs_task_name", "agent_runs", ["task_name"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])

    # ------------------------------------------------------------- standups
    op.create_table(
        "standups",
        sa.Column("id", UUID, nullable=False),
        sa.Column("engagement_id", UUID, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("for_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("summary_markdown", sa.Text, nullable=False),
        sa.Column("per_person", JSONB, nullable=False),
        sa.Column("blockers", JSONB, nullable=False),
        sa.Column("highlights", JSONB, nullable=False),
        sa.Column("citations", JSONB, nullable=False),
        sa.Column("metrics", JSONB, nullable=False),
        sa.Column("model", sa.String(64)),
        sa.Column("grounding_ratio", sa.Float),
        sa.Column("generated_at", TS),
        sa.Column("posted_at", TS),
        sa.Column("post_target", sa.String(255)),
        sa.Column("error", sa.Text),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_standups"),
        sa.ForeignKeyConstraint(
            ["engagement_id"],
            ["engagements.id"],
            name="fk_standups_engagement_id_engagements",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "engagement_id", "kind", "for_date", name="uq_standups_engagement_kind_for_date"
        ),
    )
    op.create_index("ix_standups_engagement_id", "standups", ["engagement_id"])

    # ----------------------------------------------------------- raid_items
    op.create_table(
        "raid_items",
        sa.Column("id", UUID, nullable=False),
        sa.Column("engagement_id", UUID, nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("mitigation", sa.Text),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("probability", sa.String(32)),
        sa.Column("impact", sa.String(32)),
        sa.Column("owner_user_id", UUID),
        sa.Column("owner_label", sa.String(255)),
        sa.Column("due_date", sa.Date),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(255)),
        sa.Column("citations", JSONB, nullable=False),
        sa.Column("external_row_ref", sa.String(128)),
        sa.Column("synced_at", TS),
        sa.Column("closed_at", TS),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_raid_items"),
        sa.ForeignKeyConstraint(
            ["engagement_id"],
            ["engagements.id"],
            name="fk_raid_items_engagement_id_engagements",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="fk_raid_items_owner_user_id_users",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
    )
    op.create_index("ix_raid_items_engagement_id", "raid_items", ["engagement_id"])
    op.create_index("ix_raid_items_type", "raid_items", ["type"])
    op.create_index("ix_raid_items_status", "raid_items", ["status"])
    # The gap scan asks "is this Jira key already in RAID" on every run.
    op.create_index("ix_raid_items_source_ref", "raid_items", ["engagement_id", "source_ref"])

    # --------------------------------------------------------- action_items
    op.create_table(
        "action_items",
        sa.Column("id", UUID, nullable=False),
        sa.Column("engagement_id", UUID, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("owner_user_id", UUID),
        sa.Column("owner_label", sa.String(255)),
        sa.Column("due_at", TS),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("completed_at", TS),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(255)),
        sa.Column("citations", JSONB, nullable=False),
        sa.Column("nudge_count", sa.Integer, nullable=False),
        sa.Column("last_nudged_at", TS),
        sa.Column("escalated_at", TS),
        sa.Column("nudges_muted", sa.Boolean, nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_action_items"),
        sa.ForeignKeyConstraint(
            ["engagement_id"],
            ["engagements.id"],
            name="fk_action_items_engagement_id_engagements",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name="fk_action_items_owner_user_id_users",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
    )
    op.create_index("ix_action_items_engagement_id", "action_items", ["engagement_id"])
    op.create_index("ix_action_items_owner_user_id", "action_items", ["owner_user_id"])
    op.create_index("ix_action_items_status", "action_items", ["status"])
    # The hourly nudge sweep scans open items by due date.
    op.create_index(
        "ix_action_items_status_due_at", "action_items", ["status", "due_at"]
    )

    # ------------------------------------------------------------ approvals
    op.create_table(
        "approvals",
        sa.Column("id", UUID, nullable=False),
        sa.Column("engagement_id", UUID, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("rationale", sa.Text),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("citations", JSONB, nullable=False),
        sa.Column("requested_by_task", sa.String(128), nullable=False),
        sa.Column("agent_run_id", UUID),
        sa.Column("expires_at", TS),
        sa.Column("decided_by_user_id", UUID),
        sa.Column("decided_at", TS),
        sa.Column("decision_note", sa.Text),
        sa.Column("edited_payload", JSONB),
        sa.Column("executed_at", TS),
        sa.Column("execution_result", JSONB),
        sa.Column("execution_error", sa.Text),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_approvals"),
        sa.ForeignKeyConstraint(
            ["engagement_id"],
            ["engagements.id"],
            name="fk_approvals_engagement_id_engagements",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name="fk_approvals_agent_run_id_agent_runs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name="fk_approvals_decided_by_user_id_users",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
    )
    op.create_index("ix_approvals_engagement_id", "approvals", ["engagement_id"])
    op.create_index("ix_approvals_status", "approvals", ["status"])
    op.create_index("ix_approvals_expires_at", "approvals", ["expires_at"])

    # --------------------------------------------------------- agent_events
    op.create_table(
        "agent_events",
        sa.Column("id", UUID, nullable=False),
        sa.Column("engagement_id", UUID),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("contract_version", sa.Integer, nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(255)),
        sa.Column("consented", sa.Boolean, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("processed_at", TS),
        sa.Column("rejection_reason", sa.Text),
        sa.Column("error", sa.Text),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_agent_events"),
        sa.ForeignKeyConstraint(
            ["engagement_id"],
            ["engagements.id"],
            name="fk_agent_events_engagement_id_engagements",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("source", "external_id", name="uq_agent_events_source_external_id"),
    )
    op.create_index("ix_agent_events_engagement_id", "agent_events", ["engagement_id"])
    op.create_index("ix_agent_events_type", "agent_events", ["type"])
    op.create_index("ix_agent_events_status", "agent_events", ["status"])

    # -------------------------------------------------------------- reports
    op.create_table(
        "reports",
        sa.Column("id", UUID, nullable=False),
        sa.Column("engagement_id", UUID, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content_markdown", sa.Text, nullable=False),
        sa.Column("sections", JSONB, nullable=False),
        sa.Column("citations", JSONB, nullable=False),
        sa.Column("storage_url", sa.String(1024)),
        sa.Column("model", sa.String(64)),
        sa.Column("approved_by_user_id", UUID),
        sa.Column("approved_at", TS),
        sa.Column("sent_at", TS),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_reports"),
        sa.ForeignKeyConstraint(
            ["engagement_id"],
            ["engagements.id"],
            name="fk_reports_engagement_id_engagements",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            name="fk_reports_approved_by_user_id_users",
            ondelete="SET NULL",
            onupdate="CASCADE",
        ),
        sa.UniqueConstraint(
            "engagement_id", "kind", "period_start", name="uq_reports_engagement_kind_period_start"
        ),
    )
    op.create_index("ix_reports_engagement_id", "reports", ["engagement_id"])


def downgrade() -> None:
    for table in (
        "reports",
        "agent_events",
        "approvals",
        "action_items",
        "raid_items",
        "standups",
        "agent_runs",
        "engagement_members",
        "engagements",
        "users",
    ):
        op.drop_table(table)
