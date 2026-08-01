"""User profile synchronisation.

Supabase owns authentication; this table owns authorisation. A row is created
the first time a verified token arrives, so there is no separate signup flow to
keep in step with Google OAuth and email OTP.
"""

from __future__ import annotations

import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from agent_pm.core.clock import utc_now
from agent_pm.core.enums import AppRole
from agent_pm.core.errors import AuthenticationError, NotFoundError
from agent_pm.core.logging import get_logger
from agent_pm.core.security import TokenClaims
from agent_pm.models.user import User
from agent_pm.repositories.user import UserRepository
from agent_pm.schemas.auth import CurrentUser, UserUpdate

logger = get_logger(__name__)


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def sync_from_claims(self, claims: TokenClaims) -> User:
        """Upsert the profile behind a verified token.

        Provider metadata is refreshed on every call so a name or avatar
        changed in Google shows up here without a re-login. ``role`` is never
        taken from the token — it is ours to set, and a claim in a JWT the user
        could influence must not grant approval rights.
        """
        user = await self.users.get(claims.user_id)

        if user is None and claims.email:
            # A placeholder created by `agent-pm seed` before this person ever
            # signed in. Supabase has now minted their real uid, so re-key the
            # row to it rather than creating a second account with the same
            # address — which the unique index on email would reject anyway.
            # The foreign keys to users.id are ON UPDATE CASCADE, so
            # memberships and ownership follow the change.
            user = await self._adopt_placeholder(claims.email.lower(), claims.user_id)

        if user is None:
            if not claims.email:
                raise AuthenticationError("Token has no email; cannot create a profile")

            # First user to sign in bootstraps as admin, otherwise there is
            # nobody who can grant anyone else a role.
            is_first = await self.users.count() == 0
            user = User(
                id=claims.user_id,
                email=claims.email.lower(),
                full_name=claims.display_name,
                avatar_url=claims.avatar_url,
                auth_provider=claims.provider,
                role=AppRole.ADMIN if is_first else AppRole.ENGINEER,
            )
            self.users.add(user)
            logger.info(
                "user_provisioned",
                extra={"user_id": str(user.id), "bootstrap_admin": is_first},
            )
        else:
            if claims.email:
                user.email = claims.email.lower()
            if claims.display_name:
                user.full_name = claims.display_name
            if claims.avatar_url:
                user.avatar_url = claims.avatar_url
            user.auth_provider = claims.provider

        user.last_seen_at = utc_now()
        await self.session.flush()
        return user

    async def _adopt_placeholder(
        self, email: str, auth_user_id: uuid.UUID
    ) -> User | None:
        """Re-key a seeded placeholder row to its real Supabase uid.

        Returns None when there is no row for this email, which is the normal
        first-sign-in path.
        """
        existing = await self.users.get_by_email(email)
        if existing is None or existing.id == auth_user_id:
            return existing

        previous_id = existing.id
        # Issued as SQL rather than by mutating the attribute: changing a
        # primary key through the identity map confuses the unit of work, and
        # the cascade has to happen in the database anyway.
        await self.session.execute(
            update(User).where(User.id == previous_id).values(id=auth_user_id)
        )
        self.session.expunge(existing)
        adopted = await self.users.get(auth_user_id)

        logger.info(
            "placeholder_user_adopted",
            extra={
                "email": email,
                "previous_id": str(previous_id),
                "auth_user_id": str(auth_user_id),
            },
        )
        return adopted

    async def get(self, user_id: uuid.UUID) -> User:
        return await self.users.get_or_raise(user_id)

    async def update(self, user_id: uuid.UUID, payload: UserUpdate) -> User:
        user = await self.get(user_id)
        for field_name, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field_name, value)
        await self.session.flush()
        return user

    async def find_by_email(self, email: str) -> User:
        user = await self.users.get_by_email(email.lower())
        if user is None:
            raise NotFoundError("No user with that email", details={"email": email})
        return user

    @staticmethod
    def to_current_user(user: User) -> CurrentUser:
        return CurrentUser(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            role=user.role,
            auth_provider=user.auth_provider,
            is_active=user.is_active,
        )
