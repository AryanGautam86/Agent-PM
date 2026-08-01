"""Auth and identity schemas.

There is no login endpoint here: the SPA authenticates directly against
Supabase (Google OAuth or email OTP) and this API only ever verifies the
resulting token. ``/auth/me`` is the profile-sync endpoint the SPA calls once
after sign-in.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from agent_pm.core.enums import AppRole, PodRole
from agent_pm.schemas.common import ORMModel


class CurrentUser(BaseModel):
    """The authenticated principal, assembled from the token plus our row."""

    id: uuid.UUID
    email: str
    full_name: str | None = None
    avatar_url: str | None = None
    role: AppRole = AppRole.ENGINEER
    auth_provider: str | None = None
    is_active: bool = True

    @property
    def can_approve(self) -> bool:
        return self.role.can_approve

    @property
    def can_modify(self) -> bool:
        return self.role.can_modify

    @property
    def is_admin(self) -> bool:
        return self.role is AppRole.ADMIN


class UserRead(ORMModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    avatar_url: str | None = None
    role: AppRole
    auth_provider: str | None = None
    is_active: bool
    last_seen_at: datetime | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: AppRole | None = None
    is_active: bool | None = None


class MemberRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    pod_role: PodRole
    jira_account_id: str | None = None
    github_login: str | None = None
    capacity_hours_per_sprint: int | None = None
    nudges_enabled: bool
    user: UserRead


class MemberCreate(BaseModel):
    email: EmailStr
    pod_role: PodRole = PodRole.ENGINEER
    jira_account_id: str | None = None
    github_login: str | None = None
    capacity_hours_per_sprint: int | None = None
