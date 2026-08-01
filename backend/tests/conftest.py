"""Shared test fixtures.

Unit tests run agent tasks against the fixture integrations, so they need no
database and no network. That is the point of the Protocol-per-integration
design: a task's behaviour is testable in isolation.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from agent_pm.agents.context import EngagementContext, MemberContext, TaskContext
from agent_pm.core.config import Settings, get_settings
from agent_pm.core.enums import PodRole
from agent_pm.integrations.registry import IntegrationRegistry


@pytest.fixture(autouse=True, name="_isolated_settings")
def _isolated_settings_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a developer's .env leak into a test run.

    Blanking the credentials also guarantees every integration resolves to its
    fixture implementation.
    """
    get_settings.cache_clear()
    for name in (
        "ANTHROPIC_API_KEY",
        "JIRA_BASE_URL",
        "JIRA_EMAIL",
        "JIRA_API_TOKEN",
        "GITHUB_TOKEN",
        "TEAMS_WEBHOOK_URL",
        "TEAMS_TENANT_ID",
        "DATABASE_URL",
        # Critical: a developer's local bypass must never leak into a test run
        # and make the auth tests pass for the wrong reason.
        "DEV_AUTH_BYPASS_EMAIL",
    ):
        monkeypatch.setenv(name, "")
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="local",
        anthropic_api_key="",
        jira_base_url="",
        github_token="",
        teams_webhook_url="",
        database_url="",
    )


@pytest.fixture
def registry(settings: Settings) -> IntegrationRegistry:
    registry = IntegrationRegistry(settings)
    assert registry.describe() == {
        "jira": "fixture",
        "github": "fixture",
        "channel": "fixture",
        "storage": "fixture",
        "llm": "fixture",
    }
    return registry


@pytest.fixture
def engagement_context() -> EngagementContext:
    return EngagementContext(
        id=uuid.uuid4(),
        slug="demo-pod",
        name="Demo Pod",
        client_name="Example Client",
        timezone="UTC",
        jira_project_key="DEMO",
        github_repo="example/demo",
        raid_workbook_url="memory://raid.xlsx",
        channel_target="",
        members=[
            MemberContext(display_name="Priya Nair", pod_role=PodRole.PRODUCT_OWNER),
            MemberContext(display_name="Daniel Okafor", pod_role=PodRole.TECH_LEAD),
            MemberContext(display_name="Mei Lin"),
            MemberContext(display_name="Tomas Vidal"),
        ],
    )


@pytest.fixture
def task_context(
    engagement_context: EngagementContext, registry: IntegrationRegistry
) -> TaskContext:
    return TaskContext(
        engagement=engagement_context,
        registry=registry,
        for_date=date(2026, 8, 1),
        trigger="test",
    )
