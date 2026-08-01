"""Allow standups to be written by a person, not only generated

Adds a topic line and an author. A standup with an author was typed by
somebody; one without was produced by the agent, and that distinction matters
when reading back a week of posts.

Revision ID: 0002_manual_standups
Revises: 0001_initial
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_manual_standups"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("standups", sa.Column("topic", sa.String(255), nullable=True))
    op.add_column(
        "standups",
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_standups_author_user_id_users",
        "standups",
        "users",
        ["author_user_id"],
        ["id"],
        ondelete="SET NULL",
        onupdate="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_standups_author_user_id_users", "standups", type_="foreignkey")
    op.drop_column("standups", "author_user_id")
    op.drop_column("standups", "topic")
