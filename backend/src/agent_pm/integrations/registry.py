"""Integration registry — the one place that chooses real vs fixture.

Nothing else in the codebase imports a concrete adapter. Tasks and services
depend on the Protocols and receive them from here, which is what makes the
system runnable with no credentials and swappable in tests (build a registry
with fixtures and hand it to the task).
"""

from __future__ import annotations

from agent_pm.core.config import Settings, get_settings
from agent_pm.core.enums import ModelTier
from agent_pm.core.logging import get_logger
from agent_pm.integrations.github.base import GitHubClient
from agent_pm.integrations.github.client import GitHubRestClient
from agent_pm.integrations.github.fixture import FixtureGitHubClient
from agent_pm.integrations.jira.base import JiraClient
from agent_pm.integrations.jira.client import JiraCloudClient
from agent_pm.integrations.jira.fixture import FixtureJiraClient
from agent_pm.integrations.llm.anthropic_client import AnthropicClient
from agent_pm.integrations.llm.base import LLMClient
from agent_pm.integrations.llm.fixture import FixtureLLMClient
from agent_pm.integrations.storage.base import DocumentStorageClient
from agent_pm.integrations.storage.fixture import FixtureStorageClient
from agent_pm.integrations.storage.graph_client import GraphStorageClient
from agent_pm.integrations.teams.base import ChannelClient
from agent_pm.integrations.teams.client import TeamsWebhookClient
from agent_pm.integrations.teams.fixture import FixtureChannelClient

logger = get_logger(__name__)


class IntegrationRegistry:
    """Lazily builds one adapter per integration and holds it for the process."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._jira: JiraClient | None = None
        self._github: GitHubClient | None = None
        self._channel: ChannelClient | None = None
        self._storage: DocumentStorageClient | None = None
        self._llm: LLMClient | None = None

    # ---- ports -----------------------------------------------------------

    @property
    def jira(self) -> JiraClient:
        if self._jira is None:
            self._jira = (
                JiraCloudClient(self.settings)
                if self.settings.jira_configured
                else FixtureJiraClient()
            )
        return self._jira

    @property
    def github(self) -> GitHubClient:
        if self._github is None:
            self._github = (
                GitHubRestClient(self.settings)
                if self.settings.github_configured
                else FixtureGitHubClient()
            )
        return self._github

    @property
    def channel(self) -> ChannelClient:
        if self._channel is None:
            self._channel = (
                TeamsWebhookClient(self.settings)
                if self.settings.teams_configured
                else FixtureChannelClient()
            )
        return self._channel

    @property
    def storage(self) -> DocumentStorageClient:
        if self._storage is None:
            graph_ready = bool(
                self.settings.teams_tenant_id
                and self.settings.teams_client_id
                and self.settings.teams_client_secret
            )
            self._storage = (
                GraphStorageClient(self.settings) if graph_ready else FixtureStorageClient()
            )
        return self._storage

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = (
                AnthropicClient(self.settings)
                if self.settings.anthropic_configured
                else FixtureLLMClient()
            )
        return self._llm

    # ---- helpers ---------------------------------------------------------

    def model_for(self, tier: ModelTier) -> str:
        """Resolve a task's declared tier to a configured model id."""
        if tier is ModelTier.NARRATIVE:
            return self.settings.anthropic_model_narrative
        return self.settings.anthropic_model_structured

    def describe(self) -> dict[str, str]:
        """Which implementation each port resolved to. Surfaced by /health."""
        return {
            "jira": "live" if self.settings.jira_configured else "fixture",
            "github": "live" if self.settings.github_configured else "fixture",
            "channel": "live" if self.settings.teams_configured else "fixture",
            "storage": "live" if self.settings.teams_tenant_id else "fixture",
            "llm": "live" if self.settings.anthropic_configured else "fixture",
        }

    async def aclose(self) -> None:
        for client in (self._jira, self._github, self._channel, self._storage, self._llm):
            if client is not None:
                await client.aclose()


_registry: IntegrationRegistry | None = None


def get_registry() -> IntegrationRegistry:
    global _registry
    if _registry is None:
        _registry = IntegrationRegistry()
        logger.info("integrations_resolved", extra=_registry.describe())
    return _registry


async def dispose_registry() -> None:
    global _registry
    if _registry is not None:
        await _registry.aclose()
    _registry = None
