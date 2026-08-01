"""Teams port.

The brief assumed native channel publishing. Off Copilot Studio that becomes an
outgoing integration, so this port is deliberately narrow: post a card, and
optionally read back reactions. Anything richer belongs in the web UI, which is
the primary human surface here — see ADR 0001.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class CardAction(BaseModel):
    """A button on a posted card.

    ``url`` deep-links into the web app rather than carrying the decision
    itself: an approval must be recorded against an authenticated user, and a
    webhook button cannot prove who clicked it.
    """

    label: str
    url: str
    style: str = "default"  # default | positive | destructive


class CardSection(BaseModel):
    heading: str | None = None
    body_markdown: str | None = None
    facts: dict[str, str] = Field(default_factory=dict)


class ChannelCard(BaseModel):
    """Channel-agnostic message. Adapters render it to their own format."""

    title: str
    subtitle: str | None = None
    sections: list[CardSection] = Field(default_factory=list)
    actions: list[CardAction] = Field(default_factory=list)
    accent: str = "default"  # default | good | warning | attention

    def to_markdown(self) -> str:
        lines = [f"**{self.title}**"]
        if self.subtitle:
            lines.append(f"_{self.subtitle}_")
        for section in self.sections:
            if section.heading:
                lines.append(f"\n**{section.heading}**")
            if section.body_markdown:
                lines.append(section.body_markdown)
            for key, value in section.facts.items():
                lines.append(f"- {key}: {value}")
        for action in self.actions:
            lines.append(f"[{action.label}]({action.url})")
        return "\n".join(lines)


class PostedMessage(BaseModel):
    message_id: str | None = None
    target: str
    delivered: bool
    detail: str | None = None


@runtime_checkable
class ChannelClient(Protocol):
    async def post_card(self, target: str, card: ChannelCard) -> PostedMessage:
        """Post to a channel. ``target`` is a webhook URL or channel id."""
        ...

    async def send_direct_message(self, user_ref: str, text: str) -> PostedMessage:
        """Nudge one person. ``user_ref`` is an email or Entra object id."""
        ...

    async def aclose(self) -> None: ...


def render_adaptive_card(card: ChannelCard) -> dict[str, Any]:
    """Render to Adaptive Card 1.5 — the format Teams webhooks accept."""
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": card.title,
            "weight": "Bolder",
            "size": "Medium",
            "wrap": True,
        }
    ]
    if card.subtitle:
        body.append(
            {
                "type": "TextBlock",
                "text": card.subtitle,
                "isSubtle": True,
                "spacing": "None",
                "wrap": True,
            }
        )

    for section in card.sections:
        if section.heading:
            body.append(
                {
                    "type": "TextBlock",
                    "text": section.heading,
                    "weight": "Bolder",
                    "separator": True,
                    "wrap": True,
                }
            )
        if section.body_markdown:
            body.append({"type": "TextBlock", "text": section.body_markdown, "wrap": True})
        if section.facts:
            body.append(
                {
                    "type": "FactSet",
                    "facts": [{"title": k, "value": v} for k, v in section.facts.items()],
                }
            )

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.5",
                    "body": body,
                    "actions": [
                        {"type": "Action.OpenUrl", "title": action.label, "url": action.url}
                        for action in card.actions
                    ],
                },
            }
        ],
    }
