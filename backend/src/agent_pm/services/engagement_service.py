"""Engagement management and the tenancy boundary.

``require_access`` is the single choke point the architecture depends on:
every engagement-scoped route resolves it before touching data.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_pm.core.clock import utc_now
from agent_pm.core.config import get_settings
from agent_pm.core.enums import ActionItemStatus, ApprovalStatus, PodRole, RaidStatus
from agent_pm.core.errors import AuthorizationError, ConflictError, NotFoundError
from agent_pm.core.logging import get_logger
from agent_pm.models.action_item import ActionItem
from agent_pm.models.approval import Approval
from agent_pm.models.engagement import Engagement
from agent_pm.models.raid import RaidItem
from agent_pm.models.standup import Standup
from agent_pm.models.user import EngagementMember
from agent_pm.repositories.engagement import EngagementRepository
from agent_pm.repositories.user import EngagementMemberRepository, UserRepository
from agent_pm.schemas.auth import CurrentUser, MemberCreate
from agent_pm.schemas.engagement import (
    EngagementCreate,
    EngagementSummary,
    EngagementUpdate,
)

logger = get_logger(__name__)


class EngagementService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.engagements = EngagementRepository(session)
        self.members = EngagementMemberRepository(session)
        self.users = UserRepository(session)

    # ---- authorisation ---------------------------------------------------

    async def require_access(
        self, engagement_id: uuid.UUID, user: CurrentUser
    ) -> Engagement:
        """Fetch an engagement the caller is entitled to see.

        Admins see everything; everyone else needs a membership row. The
        404-vs-403 distinction is deliberate: a non-member is told the
        engagement does not exist, so the API does not confirm which
        engagements a stranger's organisation is running.
        """
        engagement = await self.engagements.get(engagement_id)
        if engagement is None:
            raise NotFoundError("Engagement not found", details={"id": str(engagement_id)})

        if user.is_admin:
            return engagement

        membership = await self.members.get_membership(engagement_id, user.id)
        if membership is None:
            logger.warning(
                "engagement_access_denied",
                extra={"engagement_id": str(engagement_id), "user_id": str(user.id)},
            )
            raise NotFoundError("Engagement not found", details={"id": str(engagement_id)})
        return engagement

    async def require_approver(
        self, engagement_id: uuid.UUID, user: CurrentUser
    ) -> Engagement:
        """Access plus the right to decide approvals."""
        engagement = await self.require_access(engagement_id, user)
        if not user.can_approve:
            raise AuthorizationError(
                "Only a product owner, delivery lead or admin can decide approvals",
                details={"role": user.role.value},
            )
        return engagement

    # ---- onboarding ------------------------------------------------------

    async def ensure_membership(self, user_id: uuid.UUID) -> Engagement | None:
        """Guarantee that whoever just signed in has somewhere to work.

        Called on every authenticated request; it is a no-op once the user
        belongs to an engagement, so the cost is one indexed lookup.

        This exists because "signed in but in no pod" was a dead end: the UI
        rendered every control with a null engagement id and each action came
        back 422. Rather than teach every page to handle that, the state is
        made unreachable.
        """
        settings = get_settings()
        if not settings.auto_join_new_users:
            return None

        existing = await self.members.list_engagement_ids_for_user(user_id)
        if existing:
            return None

        target: Engagement | None = None
        if settings.default_engagement_slug:
            target = await self.engagements.get_by_slug(settings.default_engagement_slug)
        if target is None:
            active = await self.engagements.list_active()
            target = active[0] if active else None

        if target is None:
            # Nothing exists yet — the very first sign-in on a fresh database.
            target = Engagement(
                slug="workspace",
                name="Workspace",
                description="Created automatically for the first user to sign in.",
            )
            self.engagements.add(target)
            await self.session.flush()
            logger.info("bootstrap_engagement_created", extra={"slug": target.slug})

        self.members.add(
            EngagementMember(
                engagement_id=target.id,
                user_id=user_id,
                pod_role=PodRole.ENGINEER,
            )
        )
        await self.session.flush()
        logger.info(
            "user_auto_joined",
            extra={"user_id": str(user_id), "engagement": target.slug},
        )
        return target

    # ---- reads -----------------------------------------------------------

    async def list_for_user(self, user: CurrentUser) -> Sequence[Engagement]:
        if user.is_admin:
            return await self.engagements.list_active()
        return await self.engagements.list_for_user(user.id)

    async def summaries(self, user: CurrentUser) -> list[EngagementSummary]:
        """Headline counts for every project the caller can see.

        One grouped query per metric rather than per project, so the dashboard
        cost does not grow with the number of projects.
        """
        engagements = list(await self.list_for_user(user))
        if not engagements:
            return []

        ids = [engagement.id for engagement in engagements]

        async def tally(stmt: Select[tuple[uuid.UUID, int]]) -> dict[uuid.UUID, int]:
            rows = await self.session.execute(stmt)
            return {row[0]: row[1] for row in rows}

        open_tasks = await tally(
            select(ActionItem.engagement_id, func.count())
            .where(
                ActionItem.engagement_id.in_(ids),
                ActionItem.status.in_(
                    [ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS]
                ),
            )
            .group_by(ActionItem.engagement_id)
        )
        done_tasks = await tally(
            select(ActionItem.engagement_id, func.count())
            .where(
                ActionItem.engagement_id.in_(ids),
                ActionItem.status == ActionItemStatus.DONE,
            )
            .group_by(ActionItem.engagement_id)
        )
        overdue_tasks = await tally(
            select(ActionItem.engagement_id, func.count())
            .where(
                ActionItem.engagement_id.in_(ids),
                ActionItem.status.in_(
                    [ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS]
                ),
                ActionItem.due_at.is_not(None),
                ActionItem.due_at < utc_now(),
            )
            .group_by(ActionItem.engagement_id)
        )
        open_raid = await tally(
            select(RaidItem.engagement_id, func.count())
            .where(RaidItem.engagement_id.in_(ids), RaidItem.status != RaidStatus.CLOSED)
            .group_by(RaidItem.engagement_id)
        )
        pending = await tally(
            select(Approval.engagement_id, func.count())
            .where(
                Approval.engagement_id.in_(ids),
                Approval.status == ApprovalStatus.PENDING,
            )
            .group_by(Approval.engagement_id)
        )
        members = await tally(
            select(EngagementMember.engagement_id, func.count())
            .where(EngagementMember.engagement_id.in_(ids))
            .group_by(EngagementMember.engagement_id)
        )
        latest = await self.session.execute(
            select(Standup.engagement_id, func.max(Standup.for_date))
            .where(Standup.engagement_id.in_(ids))
            .group_by(Standup.engagement_id)
        )
        last_standup = {row[0]: row[1] for row in latest}

        return [
            EngagementSummary(
                id=engagement.id,
                name=engagement.name,
                slug=engagement.slug,
                client_name=engagement.client_name,
                agent_identity=engagement.agent_identity,
                open_tasks=open_tasks.get(engagement.id, 0),
                done_tasks=done_tasks.get(engagement.id, 0),
                overdue_tasks=overdue_tasks.get(engagement.id, 0),
                open_raid=open_raid.get(engagement.id, 0),
                pending_approvals=pending.get(engagement.id, 0),
                members=members.get(engagement.id, 0),
                last_standup_on=(
                    last_standup[engagement.id].isoformat()
                    if last_standup.get(engagement.id)
                    else None
                ),
            )
            for engagement in engagements
        ]

    async def get_members(self, engagement_id: uuid.UUID) -> Sequence[EngagementMember]:
        return await self.members.list_members(engagement_id)

    # ---- writes ----------------------------------------------------------

    async def create(self, payload: EngagementCreate, creator: CurrentUser) -> Engagement:
        if await self.engagements.slug_taken(payload.slug):
            raise ConflictError(
                "An engagement with that slug already exists",
                details={"slug": payload.slug},
            )

        engagement = Engagement(**payload.model_dump())
        self.engagements.add(engagement)
        await self.session.flush()

        # The creator joins as delivery lead, otherwise they immediately lose
        # access to what they just made.
        self.members.add(
            EngagementMember(
                engagement_id=engagement.id,
                user_id=creator.id,
                pod_role=PodRole.DELIVERY_LEAD,
            )
        )
        await self.session.flush()
        logger.info("engagement_created", extra={"slug": engagement.slug})
        return engagement

    async def update(
        self, engagement_id: uuid.UUID, payload: EngagementUpdate, user: CurrentUser
    ) -> Engagement:
        engagement = await self.require_access(engagement_id, user)
        for field_name, value in payload.model_dump(exclude_unset=True).items():
            setattr(engagement, field_name, value)
        await self.session.flush()
        return engagement

    async def add_member(
        self, engagement_id: uuid.UUID, payload: MemberCreate, user: CurrentUser
    ) -> EngagementMember:
        await self.require_access(engagement_id, user)

        member_user = await self.users.get_by_email(payload.email.lower())
        if member_user is None:
            raise NotFoundError(
                "That person has not signed in yet, so there is no account to "
                "add. Ask them to sign in once first.",
                details={"email": payload.email},
            )

        existing = await self.members.get_membership(engagement_id, member_user.id)
        if existing is not None:
            raise ConflictError("That person is already in this pod")

        membership = EngagementMember(
            engagement_id=engagement_id,
            user_id=member_user.id,
            pod_role=payload.pod_role,
            jira_account_id=payload.jira_account_id,
            github_login=payload.github_login,
            capacity_hours_per_sprint=payload.capacity_hours_per_sprint,
        )
        self.members.add(membership)
        await self.session.flush()
        return membership

    async def archive(self, engagement_id: uuid.UUID, user: CurrentUser) -> Engagement:
        """Retire a project without destroying its history.

        Deliberately not a DELETE. An engagement is the parent of every
        standup, RAID item, approval and agent run, all of which cascade — so
        removing one would erase the audit trail proving who approved what.
        Archiving hides it everywhere (all listings filter on is_active) while
        keeping that record intact.
        """
        engagement = await self.require_access(engagement_id, user)
        engagement.is_active = False
        await self.session.flush()
        logger.info("engagement_archived", extra={"slug": engagement.slug})
        return engagement

    async def remove_member(
        self, engagement_id: uuid.UUID, user_id: uuid.UUID, user: CurrentUser
    ) -> None:
        await self.require_access(engagement_id, user)
        membership = await self.members.get_membership(engagement_id, user_id)
        if membership is None:
            raise NotFoundError("That person is not in this pod")
        await self.members.remove(membership)
