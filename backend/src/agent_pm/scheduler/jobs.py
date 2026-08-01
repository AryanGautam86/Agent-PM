"""Scheduled work.

Cadence is per-engagement, because pods live in different timezones. Rather
than registering a cron entry per engagement per task — which would need
re-registering whenever a schedule changes — a single tick runs every minute
and asks each engagement whether its local time has passed the trigger.

Two properties make that safe:

* standup generation is idempotent on (engagement, kind, date), so a tick that
  fires twice cannot double-post;
* once-a-day tasks check the ``agent_runs`` audit for a success today.

Each engagement gets its own session and transaction, so one pod's failure
cannot roll back another pod's post.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from agent_pm.core.clock import is_working_day, local_now, local_today, utc_now
from agent_pm.core.config import get_settings
from agent_pm.core.enums import ReportKind, StandupKind
from agent_pm.core.errors import AgentPMError
from agent_pm.core.logging import get_logger
from agent_pm.db.session import session_scope
from agent_pm.models.engagement import Engagement
from agent_pm.repositories.engagement import EngagementRepository
from agent_pm.repositories.run import AgentRunRepository
from agent_pm.schemas.agent import StandupGenerateRequest
from agent_pm.schemas.report import ReportGenerateRequest
from agent_pm.services.action_item_service import ActionItemService
from agent_pm.services.approval_service import ApprovalService
from agent_pm.services.raid_service import RaidService
from agent_pm.services.report_service import ReportService
from agent_pm.services.standup_service import StandupService

logger = get_logger(__name__)

EngagementJob = Callable[[AsyncSession, Engagement], Awaitable[None]]


async def _for_each_active(job_name: str, job: EngagementJob) -> None:
    """Run a job once per active engagement, isolating failures."""
    async with session_scope() as session:
        engagements = list(await EngagementRepository(session).list_active())

    for engagement in engagements:
        try:
            async with session_scope() as session:
                fresh = await EngagementRepository(session).get(engagement.id)
                if fresh is None:
                    continue
                await job(session, fresh)
        except AgentPMError as exc:
            logger.error(
                "scheduled_job_failed",
                extra={
                    "job": job_name,
                    "engagement": engagement.slug,
                    "error": exc.message,
                },
            )
        except Exception:
            logger.exception(
                "scheduled_job_crashed",
                extra={"job": job_name, "engagement": engagement.slug},
            )


async def _ran_successfully_today(
    session: AsyncSession, engagement: Engagement, task_name: str
) -> bool:
    last = await AgentRunRepository(session).last_successful(engagement.id, task_name)
    if last is None:
        return False
    return last.started_at.astimezone().date() >= local_today(engagement.timezone)


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------


async def tick_standups() -> None:
    """Post the morning plan and EOD summary once each local trigger passes."""

    async def job(session: AsyncSession, engagement: Engagement) -> None:
        now = local_now(engagement.timezone)
        today = now.date()
        if not is_working_day(today):
            return

        service = StandupService(session)

        for kind, trigger_time in (
            (StandupKind.MORNING, engagement.morning_post_time),
            (StandupKind.EOD, engagement.eod_post_time),
        ):
            if now.time() < trigger_time:
                continue
            if not engagement.task_enabled(
                "morning_sprint_plan" if kind is StandupKind.MORNING else "eod_summary"
            ):
                continue

            _, outcome = await service.generate(
                engagement.id,
                kind,
                StandupGenerateRequest(for_date=today),
                trigger="schedule",
            )
            if outcome is not None:
                logger.info(
                    "scheduled_standup_generated",
                    extra={
                        "engagement": engagement.slug,
                        "kind": kind.value,
                        "posted": outcome.posted,
                    },
                )

    await _for_each_active("tick_standups", job)


async def daily_raid_gap_scan() -> None:
    """Once per working day, after the morning Jira pull."""

    async def job(session: AsyncSession, engagement: Engagement) -> None:
        now = local_now(engagement.timezone)
        if not is_working_day(now.date()) or now.time() < engagement.morning_post_time:
            return
        if not engagement.task_enabled("raid_gap_scan"):
            return
        if await _ran_successfully_today(session, engagement, "raid_gap_scan"):
            return

        result = await RaidService(session).run_gap_scan(engagement.id, trigger="schedule")
        logger.info(
            "scheduled_gap_scan",
            extra={"engagement": engagement.slug, "gaps": result.gaps_found},
        )

    await _for_each_active("daily_raid_gap_scan", job)


async def daily_risk_promotion() -> None:
    async def job(session: AsyncSession, engagement: Engagement) -> None:
        now = local_now(engagement.timezone)
        if not is_working_day(now.date()) or now.time() < engagement.morning_post_time:
            return
        if not engagement.task_enabled("blocker_risk_promotion"):
            return
        if await _ran_successfully_today(session, engagement, "blocker_risk_promotion"):
            return

        created = await RaidService(session).run_risk_promotion(
            engagement.id, trigger="schedule"
        )
        if created:
            logger.info(
                "scheduled_risk_promotion",
                extra={"engagement": engagement.slug, "proposed": created},
            )

    await _for_each_active("daily_risk_promotion", job)


async def hourly_nudge_sweep() -> None:
    async def job(session: AsyncSession, engagement: Engagement) -> None:
        if not engagement.task_enabled("action_item_tracking"):
            return
        result = await ActionItemService(session).run_nudge_sweep(
            engagement.id, trigger="schedule"
        )
        if result.nudged or result.escalated:
            logger.info(
                "scheduled_nudge_sweep",
                extra={
                    "engagement": engagement.slug,
                    "nudged": result.nudged,
                    "escalated": result.escalated,
                },
            )

    await _for_each_active("hourly_nudge_sweep", job)


async def weekly_status_reports() -> None:
    """Draft the client status on the engagement's configured weekday."""

    async def job(session: AsyncSession, engagement: Engagement) -> None:
        now = local_now(engagement.timezone)
        if now.weekday() != engagement.weekly_status_weekday:
            return
        if now.time() < engagement.eod_post_time:
            return
        if not engagement.task_enabled("weekly_client_status"):
            return
        if await _ran_successfully_today(session, engagement, "weekly_client_status"):
            return

        report = await ReportService(session).generate(
            engagement.id,
            ReportKind.WEEKLY_STATUS,
            ReportGenerateRequest(period_end=now.date()),
            trigger="schedule",
        )
        logger.info(
            "scheduled_weekly_status",
            extra={"engagement": engagement.slug, "report_id": str(report.id)},
        )

    await _for_each_active("weekly_status_reports", job)


async def expire_approvals() -> None:
    """Auto-deny approvals nobody decided in time. Global, not per-engagement."""
    async with session_scope() as session:
        expired = await ApprovalService(session).expire_stale()
    if expired:
        logger.info("approvals_auto_denied", extra={"count": expired})


async def heartbeat() -> None:
    """Proof of life. Without it, a wedged worker looks the same as a quiet one."""
    settings = get_settings()
    logger.info(
        "scheduler_heartbeat",
        extra={"at": utc_now().isoformat(), "environment": settings.environment.value},
    )
