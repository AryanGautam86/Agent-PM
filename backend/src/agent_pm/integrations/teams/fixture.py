"""In-memory channel.

Records what would have been posted. In local development this is what runs,
so the standup pipeline is fully exercisable without a Teams tenant — the posts
are visible in the web UI and in the log.
"""

from __future__ import annotations

from agent_pm.core.logging import get_logger
from agent_pm.integrations.teams.base import ChannelCard, PostedMessage

logger = get_logger(__name__)


class FixtureChannelClient:
    """Implements :class:`~agent_pm.integrations.teams.base.ChannelClient`."""

    name = "teams-fixture"

    def __init__(self) -> None:
        self.posted: list[tuple[str, ChannelCard]] = []
        self.direct_messages: list[tuple[str, str]] = []

    async def post_card(self, target: str, card: ChannelCard) -> PostedMessage:
        self.posted.append((target, card))
        logger.info(
            "channel_card_simulated",
            extra={"target": target or "local", "title": card.title},
        )
        return PostedMessage(
            message_id=f"fixture-{len(self.posted)}",
            target=target or "local",
            delivered=True,
            detail="simulated",
        )

    async def send_direct_message(self, user_ref: str, text: str) -> PostedMessage:
        self.direct_messages.append((user_ref, text))
        logger.info("channel_dm_simulated", extra={"user_ref": user_ref})
        return PostedMessage(
            message_id=f"fixture-dm-{len(self.direct_messages)}",
            target=user_ref,
            delivered=True,
            detail="simulated",
        )

    async def aclose(self) -> None:
        return None
