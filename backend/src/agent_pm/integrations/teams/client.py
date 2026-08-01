"""Teams adapter over an incoming webhook.

The simple half of the Teams story: posting works with nothing but a webhook
URL per channel. Reading messages and reactions, and sending direct messages,
need a Graph app registration — see :class:`TeamsWebhookClient.send_direct_message`.
"""

from __future__ import annotations

from agent_pm.core.config import Settings
from agent_pm.core.errors import IntegrationError, IntegrationNotConfiguredError
from agent_pm.core.logging import get_logger
from agent_pm.integrations.base import HttpIntegration
from agent_pm.integrations.teams.base import ChannelCard, PostedMessage, render_adaptive_card

logger = get_logger(__name__)


class TeamsWebhookClient(HttpIntegration):
    name = "teams"

    def __init__(self, settings: Settings) -> None:
        super().__init__(headers={"Content-Type": "application/json"})
        self._default_webhook = settings.teams_webhook_url
        self._graph_configured = bool(
            settings.teams_tenant_id and settings.teams_client_id and settings.teams_client_secret
        )

    async def post_card(self, target: str, card: ChannelCard) -> PostedMessage:
        webhook = target or self._default_webhook
        if not webhook.startswith("http"):
            raise IntegrationError(
                "teams",
                "post_card needs a webhook URL; a bare channel id requires the "
                "Graph adapter, which is not implemented yet",
                details={"target": target},
            )

        await self.post(webhook, json=render_adaptive_card(card))
        logger.info("teams_card_posted", extra={"title": card.title})
        # Incoming webhooks return no message id, so there is nothing to
        # correlate a later reaction against. That is a known limitation of
        # this adapter, not of the design.
        return PostedMessage(message_id=None, target=webhook, delivered=True)

    async def send_direct_message(self, user_ref: str, text: str) -> PostedMessage:
        raise IntegrationNotConfiguredError(
            "teams",
            "Direct messages require Microsoft Graph (chats.create + "
            "chatMessage.send) with an app registration. Configure "
            "TEAMS_TENANT_ID / TEAMS_CLIENT_ID / TEAMS_CLIENT_SECRET and "
            "implement the Graph adapter.",
            details={"user_ref": user_ref, "graph_configured": self._graph_configured},
        )
