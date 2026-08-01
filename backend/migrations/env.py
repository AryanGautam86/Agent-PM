"""Alembic environment.

Reads the database URL from application settings rather than alembic.ini, and
uses the direct (non-pooler) Supabase connection — the transaction pooler does
not support the session-level operations DDL needs.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from agent_pm.core.config import get_settings

# Importing the package registers every mapper on Base.metadata.
from agent_pm.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()
if not settings.migration_database_url:
    raise RuntimeError(
        "No database URL. Set ALEMBIC_DATABASE_URL (direct connection, port "
        "5432) or DATABASE_URL in backend/.env"
    )
config.set_main_option("sqlalchemy.url", settings.migration_database_url)


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Supabase manages auth, storage and other schemas in the same
        # database; autogenerate must not try to drop them.
        include_schemas=False,
    )


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
