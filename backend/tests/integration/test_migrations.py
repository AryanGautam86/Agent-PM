"""Migration parity.

Asserts that applying every migration to an empty database produces exactly
the schema the models describe. Without this, `alembic revision
--autogenerate` silently drifts from the ORM and the first sign of trouble is
a production 500 on a missing column.

Needs a real Postgres — the models use JSONB and `timestamptz`, so SQLite
cannot stand in.

**These tests drop every table.** They therefore refuse to use `DATABASE_URL`,
and read `ALEMBIC_TEST_DATABASE_URL` instead: a separate, deliberately-set
variable pointing at a throwaway database. Without that, running `make test`
on a laptop would silently destroy the developer's seeded data. CI sets it.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import create_async_engine

from agent_pm.core.config import get_settings
from agent_pm.models import Base

pytestmark = pytest.mark.integration


def _resolve_migration_url() -> str:
    """Read at import time, before the isolation fixture blanks the env.

    Only ``ALEMBIC_TEST_DATABASE_URL`` is honoured. Falling back to
    ``DATABASE_URL`` would mean these destructive tests target whatever
    database the developer is actually using, which is exactly the accident
    this guard exists to prevent.
    """
    return os.getenv("ALEMBIC_TEST_DATABASE_URL", "")


MIGRATION_URL = _resolve_migration_url()

pytest_skip = pytest.mark.skipif(
    not MIGRATION_URL,
    reason=(
        "destructive: set ALEMBIC_TEST_DATABASE_URL to a throwaway database "
        "to run these"
    ),
)


@pytest.fixture(autouse=True)
def _restore_database_url(
    monkeypatch: pytest.MonkeyPatch, _isolated_settings: None
) -> None:
    """Point this module's Alembic runs at the throwaway database.

    conftest blanks every credential so unit tests cannot touch anything real.
    These tests are the exception: Alembic's env.py reads the URL through the
    same settings object, so it has to be put back — as the *test* URL, never
    the developer's.
    """
    monkeypatch.setenv("DATABASE_URL", MIGRATION_URL)
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", MIGRATION_URL)
    get_settings.cache_clear()

# Objects Supabase or Postgres own, which autogenerate would otherwise offer to
# drop because they are absent from our metadata.
IGNORED_TABLES = {"alembic_version", "spatial_ref_sys"}


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", MIGRATION_URL)
    return config


def _relevant(diffs: list[Any]) -> list[Any]:
    """Drop diffs about tables we deliberately do not model."""
    keep: list[Any] = []
    for diff in diffs:
        entry = diff[0] if isinstance(diff, tuple) else diff
        name = str(entry)
        if any(ignored in name for ignored in IGNORED_TABLES):
            continue
        keep.append(diff)
    return keep


@pytest_skip
async def test_migrations_apply_from_empty_and_match_the_models() -> None:
    # env.py calls asyncio.run(), so the upgrade has to happen off this loop.
    await asyncio.to_thread(command.downgrade, _alembic_config(), "base")
    await asyncio.to_thread(command.upgrade, _alembic_config(), "head")

    engine = create_async_engine(MIGRATION_URL)
    try:
        async with engine.connect() as connection:
            diffs = await connection.run_sync(_diff_against_models)
    finally:
        await engine.dispose()

    assert _relevant(diffs) == [], (
        "The migrations and the models disagree. Run "
        "`alembic revision --autogenerate` and commit the result."
    )


def _diff_against_models(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(
        connection, opts={"compare_type": True, "compare_server_default": True}
    )
    return compare_metadata(context, Base.metadata)


@pytest_skip
async def test_every_model_table_exists_after_upgrade() -> None:
    await asyncio.to_thread(command.upgrade, _alembic_config(), "head")

    engine = create_async_engine(MIGRATION_URL)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            present = {row[0] for row in result}
    finally:
        await engine.dispose()

    expected = set(Base.metadata.tables)
    assert expected <= present, f"missing tables: {sorted(expected - present)}"


@pytest_skip
async def test_downgrade_removes_everything() -> None:
    """A migration that cannot be rolled back is a migration you cannot deploy."""
    await asyncio.to_thread(command.upgrade, _alembic_config(), "head")
    await asyncio.to_thread(command.downgrade, _alembic_config(), "base")

    engine = create_async_engine(MIGRATION_URL)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
            present = {row[0] for row in result} - IGNORED_TABLES
    finally:
        await engine.dispose()

    assert present == set(), f"left behind: {sorted(present)}"
