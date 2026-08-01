"""A2A event contract.

The inbound envelope is versioned and validated at the edge. Anything that
does not match is stored with ``status=rejected`` and a reason, rather than
being dropped — a Meeting Agent that starts sending a shape we do not
understand should be visible, not silent.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agent_pm.core.enums import EventStatus, EventType
from agent_pm.schemas.common import ORMModel

SUPPORTED_CONTRACT_VERSIONS = frozenset({1})


class MeetingOutcomeEnvelope(BaseModel):
    """What the Meeting Agent POSTs to ``/events/meeting-outcome``."""

    type: EventType = EventType.MEETING_OUTCOME
    version: int = 1
    engagement_slug: str
    external_id: str = Field(
        description="Stable id for this meeting. Redelivery with the same id "
        "is ignored rather than reprocessed."
    )
    consented: bool = Field(
        description="Set by the Meeting Agent's consent flow. False is "
        "rejected at intake — this agent never processes unconsented data."
    )
    occurred_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EventRead(ORMModel):
    id: uuid.UUID
    engagement_id: uuid.UUID | None = None
    type: EventType
    contract_version: int
    direction: str
    source: str
    external_id: str | None = None
    consented: bool
    payload: dict[str, Any] = Field(default_factory=dict)
    status: EventStatus
    processed_at: datetime | None = None
    rejection_reason: str | None = None
    error: str | None = None
    created_at: datetime


class EventIntakeResult(BaseModel):
    event_id: uuid.UUID
    status: EventStatus
    duplicate: bool = False
    approvals_created: int = 0
    action_items_created: int = 0
    message: str | None = None
