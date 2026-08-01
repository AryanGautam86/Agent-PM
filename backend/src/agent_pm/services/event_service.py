"""Agent-to-agent event bus.

Inbound: ``meeting_outcome`` from the Meeting Agent.
Outbound: ``pm_summary`` / ``pm_eod_summary`` for downstream consumers.

Both directions are persisted. Rejected envelopes are stored with a reason
rather than discarded, because "we never received it" and "we refused it" are
different answers and the audit needs to tell them apart.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent_pm.core.clock import utc_now
from agent_pm.core.config import Settings, get_settings
from agent_pm.core.enums import EventStatus, EventType
from agent_pm.core.errors import ConsentError, EventContractError, NotFoundError
from agent_pm.core.logging import get_logger
from agent_pm.models.event import AgentEvent
from agent_pm.repositories.engagement import EngagementRepository
from agent_pm.repositories.event import AgentEventRepository
from agent_pm.schemas.event import (
    SUPPORTED_CONTRACT_VERSIONS,
    EventIntakeResult,
    MeetingOutcomeEnvelope,
)

logger = get_logger(__name__)

MEETING_AGENT_SOURCE = "meeting-agent"
PM_AGENT_SOURCE = "pm-agent"


class EventService:
    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.events = AgentEventRepository(session)
        self.engagements = EngagementRepository(session)

    # ---- outbound --------------------------------------------------------

    async def emit(
        self,
        event_type: EventType,
        *,
        engagement_id: uuid.UUID | None,
        payload: dict[str, Any],
    ) -> AgentEvent:
        event = AgentEvent(
            engagement_id=engagement_id,
            type=event_type,
            contract_version=1,
            direction="outbound",
            source=PM_AGENT_SOURCE,
            external_id=f"{event_type.value}:{uuid.uuid4()}",
            consented=True,
            payload=payload,
            status=EventStatus.PROCESSED,
            processed_at=utc_now(),
        )
        self.events.add(event)
        await self.session.flush()
        logger.info("event_emitted", extra={"type": event_type.value})
        return event

    # ---- inbound ---------------------------------------------------------

    def verify_signature(self, raw_body: bytes, signature: str | None) -> None:
        """HMAC-SHA256 over the raw body, if a shared secret is configured.

        Compared with ``compare_digest`` so a wrong signature costs the same
        time as a right one.
        """
        secret = self.settings.meeting_agent_webhook_secret
        if not secret:
            return
        if not signature:
            raise EventContractError("Missing X-Signature header")

        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        provided = signature.removeprefix("sha256=")
        if not hmac.compare_digest(expected, provided):
            raise EventContractError("Signature does not match")

    async def receive_meeting_outcome(
        self, envelope: MeetingOutcomeEnvelope
    ) -> tuple[AgentEvent, EventIntakeResult]:
        """Store and validate an inbound envelope.

        Processing happens separately (``services/meeting_service.py``) so that
        a slow or failing downstream never makes the Meeting Agent's POST time
        out and retry.
        """
        duplicate = await self.events.find_by_external_id(
            MEETING_AGENT_SOURCE, envelope.external_id
        )
        if duplicate is not None:
            return duplicate, EventIntakeResult(
                event_id=duplicate.id,
                status=duplicate.status,
                duplicate=True,
                message="Already received; ignoring redelivery.",
            )

        engagement = await self.engagements.get_by_slug(envelope.engagement_slug)

        event = AgentEvent(
            engagement_id=engagement.id if engagement else None,
            type=EventType.MEETING_OUTCOME,
            contract_version=envelope.version,
            direction="inbound",
            source=MEETING_AGENT_SOURCE,
            external_id=envelope.external_id,
            consented=envelope.consented,
            payload=envelope.payload,
            status=EventStatus.RECEIVED,
        )
        self.events.add(event)

        rejection = self._rejection_reason(envelope, engagement is not None)
        if rejection is not None:
            event.status = EventStatus.REJECTED
            event.rejection_reason = rejection
            event.processed_at = utc_now()
            await self.session.flush()
            logger.warning(
                "meeting_outcome_rejected",
                extra={"external_id": envelope.external_id, "reason": rejection},
            )
            return event, EventIntakeResult(
                event_id=event.id, status=event.status, message=rejection
            )

        await self.session.flush()
        return event, EventIntakeResult(event_id=event.id, status=event.status)

    @staticmethod
    def _rejection_reason(
        envelope: MeetingOutcomeEnvelope, engagement_known: bool
    ) -> str | None:
        if not envelope.consented:
            # The consent gate. Never process meeting data the participants
            # did not agree to share.
            return "Envelope is not marked consented"
        if envelope.version not in SUPPORTED_CONTRACT_VERSIONS:
            return (
                f"Unsupported contract version {envelope.version}; "
                f"supported: {sorted(SUPPORTED_CONTRACT_VERSIONS)}"
            )
        if not engagement_known:
            return f"Unknown engagement slug {envelope.engagement_slug!r}"
        return None

    def assert_processable(self, event: AgentEvent) -> None:
        """Guard used again at processing time, not only at intake."""
        if not event.consented:
            raise ConsentError("Refusing to process an unconsented meeting outcome")
        if event.contract_version not in SUPPORTED_CONTRACT_VERSIONS:
            raise EventContractError(
                f"Unsupported contract version {event.contract_version}"
            )
        if event.engagement_id is None:
            raise NotFoundError("Event is not bound to a known engagement")

    # ---- reads -----------------------------------------------------------

    async def mark_processed(
        self, event: AgentEvent, *, error: str | None = None
    ) -> AgentEvent:
        event.status = EventStatus.FAILED if error else EventStatus.PROCESSED
        event.error = error
        event.processed_at = utc_now()
        await self.session.flush()
        return event
