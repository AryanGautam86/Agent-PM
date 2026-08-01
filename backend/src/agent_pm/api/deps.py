"""FastAPI dependencies.

Request-scoped wiring only: a database session, the authenticated principal,
and pagination. Business rules live in services — a dependency that starts
making decisions is a service in disguise.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from agent_pm.core.config import Settings, get_settings
from agent_pm.core.errors import AuthenticationError, AuthorizationError
from agent_pm.core.logging import get_logger
from agent_pm.core.security import TokenClaims, extract_bearer_token, verify_token
from agent_pm.db.session import get_session_factory
from agent_pm.schemas.auth import CurrentUser
from agent_pm.services.user_service import UserService

logger = get_logger(__name__)


async def get_db() -> AsyncIterator[AsyncSession]:
    """One transaction per request.

    Commits when the handler returns normally, rolls back on any exception, so
    a route cannot half-apply a change by forgetting to commit.
    """
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def _dev_claims(settings: Settings) -> TokenClaims:
    """Synthetic claims for the local-only bypass.

    The id is derived from the email so the same developer maps to the same
    row across restarts, and so it cannot collide with a real Supabase uid.
    """
    email = settings.dev_auth_bypass_email
    return TokenClaims(
        sub=uuid.uuid5(uuid.NAMESPACE_URL, f"agent-pm-dev:{email}"),
        email=email,
        aud=settings.supabase_jwt_audience,
        exp=datetime.now(UTC) + timedelta(hours=1),
        app_metadata={"provider": "dev-bypass"},
        user_metadata={"full_name": email.split("@")[0].replace(".", " ").title()},
    )


async def get_token_claims(
    settings: AppSettings,
    authorization: Annotated[str | None, Header()] = None,
) -> TokenClaims:
    """Establish who is calling, without touching the database.

    Deliberately a separate dependency, and deliberately listed before the
    session in ``get_current_user``: an unauthenticated request must be
    rejected without opening a connection, so a database outage returns 401 to
    a caller with no token rather than 500.
    """
    if settings.dev_auth_bypass_active:
        # Logged on every request on purpose: an API running without
        # authentication should never be quiet about it, even locally.
        logger.warning(
            "auth_bypassed_dev_only",
            extra={"email": settings.dev_auth_bypass_email},
        )
        return _dev_claims(settings)

    return await verify_token(extract_bearer_token(authorization), settings)


TokenClaimsDep = Annotated[TokenClaims, Depends(get_token_claims)]


async def get_current_user(claims: TokenClaimsDep, session: DbSession) -> CurrentUser:
    """Verified identity → synced profile row → principal.

    The profile is upserted here rather than in a separate signup flow, so
    Google OAuth and email OTP both land a usable account on first request.
    """
    service = UserService(session)
    user = await service.sync_from_claims(claims)
    if not user.is_active:
        raise AuthenticationError("This account has been deactivated")

    # Anyone who can authenticate can use the product: give them a workspace
    # rather than a dead end. No-op once they belong to one.
    from agent_pm.services.engagement_service import EngagementService

    await EngagementService(session).ensure_membership(user.id)

    return service.to_current_user(user)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


async def require_admin(user: CurrentUserDep) -> CurrentUser:
    if not user.is_admin:
        raise AuthorizationError("Administrator access required")
    return user


AdminUserDep = Annotated[CurrentUser, Depends(require_admin)]


class Pagination:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset


PaginationDep = Annotated[Pagination, Depends(Pagination)]
