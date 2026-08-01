"""A2A endpoints.

The meeting-outcome webhook is the one unauthenticated route in the API: it is
called by another service, not a person, so it is protected by an HMAC
signature over the raw body rather than by a Supabase token.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Header, Query, Request

from agent_pm.api.deps import CurrentUserDep, DbSession, PaginationDep
from agent_pm.core.enums import EventType
from agent_pm.core.errors import AgentPMError
from agent_pm.core.logging import get_logger
from agent_pm.schemas.event import EventIntakeResult, EventRead, MeetingOutcomeEnvelope
from agent_pm.services.engagement_service import EngagementService
from agent_pm.services.event_service import EventService
from agent_pm.services.meeting_service import MeetingService

logger = get_logger(__name__)

router = APIRouter(tags=["events"])


@router.post(
    "/events/meeting-outcome",
    response_model=EventIntakeResult,
    summary="Receive a meeting outcome from the Meeting Agent",
)
async def receive_meeting_outcome(
    request: Request,
    envelope: MeetingOutcomeEnvelope,
    session: DbSession,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
) -> EventIntakeResult:
    """Store, validate, then process.

    Intake and processing are separate so a duplicate delivery is cheap and a
    slow model call cannot make the caller time out and retry. Processing
    failures are recorded on the event, not returned as a 5xx, because a retry
    would re-deliver data we have already accepted.
    """
    events = EventService(session)
    events.verify_signature(await request.body(), x_signature)

    event, result = await events.receive_meeting_outcome(envelope)
    if result.duplicate or event.status.value == "rejected":
        return result

    try:
        return await MeetingService(session).process(event)
    except AgentPMError as exc:
        logger.error(
            "meeting_outcome_processing_failed",
            extra={"event_id": str(event.id), "error": exc.message},
        )
        return EventIntakeResult(
            event_id=event.id, status=event.status, message=exc.message
        )


@router.get(
    "/engagements/{engagement_id}/events",
    response_model=list[EventRead],
    summary="List A2A events",
)
async def list_events(
    engagement_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSession,
    page: PaginationDep,
    event_type: EventType | None = Query(default=None, alias="type"),
) -> list[EventRead]:
    await EngagementService(session).require_access(engagement_id, user)
    events = await EventService(session).events.list_for_engagement(
        engagement_id, event_type=event_type, limit=page.limit, offset=page.offset
    )
    return [EventRead.model_validate(event) for event in events]
