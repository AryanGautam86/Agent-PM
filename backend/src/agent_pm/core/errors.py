"""Application error hierarchy.

Services and agents raise these; ``api.error_handlers`` is the only place that
knows how they map to HTTP. Keeping the mapping in one place means a service
never imports ``fastapi.HTTPException``.
"""

from __future__ import annotations

from typing import Any


class AgentPMError(Exception):
    """Base class for every deliberate failure in this application."""

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


# --------------------------------------------------------------------------
# Client errors
# --------------------------------------------------------------------------


class NotFoundError(AgentPMError):
    status_code = 404
    code = "not_found"


class ConflictError(AgentPMError):
    status_code = 409
    code = "conflict"


class ValidationError(AgentPMError):
    status_code = 422
    code = "validation_error"


class AuthenticationError(AgentPMError):
    status_code = 401
    code = "unauthenticated"


class AuthorizationError(AgentPMError):
    status_code = 403
    code = "forbidden"


class RateLimitedError(AgentPMError):
    status_code = 429
    code = "rate_limited"


# --------------------------------------------------------------------------
# Domain errors
# --------------------------------------------------------------------------


class GroundingError(AgentPMError):
    """Agent output failed the citation requirement.

    This is the mechanism behind the brief's "< 1% hallucination rate" KPI: a
    task whose claims are not traceable to a Jira key, commit, message id or
    transcript timestamp is discarded rather than posted.
    """

    status_code = 422
    code = "grounding_failed"


class AutonomyViolationError(AgentPMError):
    """A task attempted an external write its autonomy level does not permit."""

    status_code = 403
    code = "autonomy_violation"


class ApprovalRequiredError(AgentPMError):
    """The requested action exists only as a pending approval."""

    status_code = 409
    code = "approval_required"


class ConsentError(AgentPMError):
    """Inbound meeting data arrived without upstream consent."""

    status_code = 403
    code = "consent_missing"


class EventContractError(AgentPMError):
    """An A2A envelope did not match a known type or version."""

    status_code = 400
    code = "event_contract_violation"


# --------------------------------------------------------------------------
# Integration errors
# --------------------------------------------------------------------------


class IntegrationError(AgentPMError):
    """An outbound system failed. Carries which one, for the audit trail."""

    status_code = 502
    code = "integration_error"

    def __init__(
        self,
        integration: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"[{integration}] {message}", details=details)
        self.integration = integration


class IntegrationNotConfiguredError(IntegrationError):
    status_code = 503
    code = "integration_not_configured"
