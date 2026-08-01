"""Scheduler process.

Run as a Render background worker:

    python -m agent_pm.scheduler.runner

Or in-process by setting ``SCHEDULER_ENABLED=true`` on the web service — but
only ever in one place at a time. Two schedulers means two morning posts.
"""

from __future__ import annotations

import asyncio
import signal

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from agent_pm.core.config import Settings, get_settings
from agent_pm.core.logging import configure_logging, get_logger
from agent_pm.db.session import dispose_engine
from agent_pm.integrations.registry import dispose_registry, get_registry
from agent_pm.scheduler import jobs

logger = get_logger(__name__)


def build_scheduler(settings: Settings | None = None) -> AsyncIOScheduler:
    settings = settings or get_settings()

    scheduler = AsyncIOScheduler(
        executors={"default": AsyncIOExecutor()},
        job_defaults={
            # If the worker was asleep, run once on wake rather than firing
            # every missed minute.
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 300,
        },
        timezone="UTC",
    )

    # The per-engagement trigger check. Cheap: one query plus an in-memory
    # time comparison per engagement.
    scheduler.add_job(
        jobs.tick_standups,
        IntervalTrigger(seconds=settings.scheduler_tick_seconds),
        id="tick_standups",
        name="Standup trigger check",
    )
    scheduler.add_job(
        jobs.daily_raid_gap_scan,
        IntervalTrigger(minutes=15),
        id="raid_gap_scan",
        name="RAID gap scan",
    )
    scheduler.add_job(
        jobs.daily_risk_promotion,
        IntervalTrigger(minutes=30),
        id="risk_promotion",
        name="Blocker to risk promotion",
    )
    scheduler.add_job(
        jobs.hourly_nudge_sweep,
        CronTrigger(minute=5),
        id="nudge_sweep",
        name="Action item nudges",
    )
    scheduler.add_job(
        jobs.weekly_status_reports,
        IntervalTrigger(minutes=30),
        id="weekly_status",
        name="Weekly client status",
    )
    scheduler.add_job(
        jobs.expire_approvals,
        CronTrigger(minute=15),
        id="expire_approvals",
        name="Auto-deny expired approvals",
    )
    scheduler.add_job(
        jobs.heartbeat,
        IntervalTrigger(minutes=30),
        id="heartbeat",
        name="Heartbeat",
    )

    return scheduler


async def main() -> None:
    settings = get_settings()
    configure_logging(settings)

    if not settings.database_configured:
        raise SystemExit("DATABASE_URL is required to run the scheduler")

    logger.info(
        "scheduler_worker_starting",
        extra={
            "environment": settings.environment.value,
            "integrations": get_registry().describe(),
        },
    )

    scheduler = build_scheduler(settings)
    scheduler.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        # Render sends SIGTERM on deploy; finish the current job, then exit.
        loop.add_signal_handler(sig, stop.set)

    try:
        await stop.wait()
    finally:
        logger.info("scheduler_worker_stopping")
        scheduler.shutdown(wait=True)
        await dispose_registry()
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
