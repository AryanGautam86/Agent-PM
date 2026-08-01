"""Identity endpoints.

There is no login route. The SPA signs in against Supabase directly — Google
OAuth or email OTP — and calls ``GET /auth/me`` once with the resulting token,
which provisions the profile row on first use.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from agent_pm.api.deps import AdminUserDep, CurrentUserDep, DbSession, PaginationDep
from agent_pm.schemas.auth import CurrentUser, UserRead, UserUpdate
from agent_pm.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=CurrentUser, summary="Current user")
async def me(user: CurrentUserDep) -> CurrentUser:
    """Verify the token and return (creating if needed) the caller's profile."""
    return user


@router.get("/users", response_model=list[UserRead], summary="List users (admin)")
async def list_users(
    _: AdminUserDep, session: DbSession, page: PaginationDep
) -> list[UserRead]:
    service = UserService(session)
    users = await service.users.find_many(limit=page.limit, offset=page.offset)
    return [UserRead.model_validate(user) for user in users]


@router.patch(
    "/users/{user_id}", response_model=UserRead, summary="Update a user (admin)"
)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    _: AdminUserDep,
    session: DbSession,
) -> UserRead:
    """Role changes live here and nowhere else.

    A role is never read from the JWT, so granting approval rights is an
    explicit administrative act rather than something a token can assert.
    """
    user = await UserService(session).update(user_id, payload)
    return UserRead.model_validate(user)
