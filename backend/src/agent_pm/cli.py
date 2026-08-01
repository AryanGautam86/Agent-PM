"""Operational CLI.

    python -m agent_pm.cli tasks
    python -m agent_pm.cli seed --slug demo-pod --name "Demo Pod" --owner you@company.com
    python -m agent_pm.cli engagements
    python -m agent_pm.cli run demo-pod morning_sprint_plan

Exists so an operator can bootstrap and inspect an engagement from a shell on
the Render worker, without going through the API and without a browser session.
Anything that mutates a client system still goes through the approval flow —
``run`` is subject to the same autonomy gate as the scheduler.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import time

from agent_pm.agents.registry import describe_catalog, get_task
from agent_pm.core.config import get_settings
from agent_pm.core.enums import AppRole, PodRole
from agent_pm.core.errors import AgentPMError
from agent_pm.core.logging import configure_logging, get_logger
from agent_pm.db.session import dispose_engine, session_scope
from agent_pm.models.engagement import Engagement
from agent_pm.models.user import EngagementMember, User
from agent_pm.repositories.engagement import EngagementRepository
from agent_pm.repositories.user import EngagementMemberRepository, UserRepository
from agent_pm.services.agent_runner import AgentRunner
from agent_pm.services.engagement_service import EngagementService

logger = get_logger(__name__)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_tasks() -> int:
    """List the catalog. The only command that needs no database."""
    print(f"\n{'TASK':<26} {'AUTONOMY':<9} {'MODEL':<11} APPROVAL")
    print("-" * 68)
    for entry in describe_catalog():
        approval = entry["approval_kind"] or "—"
        print(
            f"{entry['name']:<26} {entry['autonomy']:<9} "
            f"{entry['model_tier']:<11} {approval}"
        )
    print()
    return 0


async def cmd_engagements() -> int:
    async with session_scope() as session:
        engagements = await EngagementRepository(session).list_active()
        if not engagements:
            print("No engagements. Create one with: python -m agent_pm.cli seed --help")
            return 0

        print(f"\n{'SLUG':<20} {'NAME':<28} {'JIRA':<10} TZ")
        print("-" * 72)
        for engagement in engagements:
            print(
                f"{engagement.slug:<20} {engagement.name:<28} "
                f"{engagement.jira_project_key or '—':<10} {engagement.timezone}"
            )
        print()
    return 0


async def cmd_seed(args: argparse.Namespace) -> int:
    """Create an engagement and its first member.

    The owner is created with a generated id when they have never signed in.
    Supabase will mint a different uid for them on first sign-in, so the row is
    matched by email and adopted then — see ``UserService.sync_from_claims``.
    """
    async with session_scope() as session:
        engagements = EngagementRepository(session)
        users = UserRepository(session)
        members = EngagementMemberRepository(session)

        if await engagements.slug_taken(args.slug):
            print(f"Engagement {args.slug!r} already exists.", file=sys.stderr)
            return 1

        owner = await users.get_by_email(args.owner.lower())
        if owner is None:
            # The very first account becomes an admin, mirroring what
            # UserService does on first sign-in. Without this, seeding would
            # leave the user table non-empty, the sign-in bootstrap would never
            # fire, and no one could ever grant anyone a role.
            is_first = await users.count() == 0
            owner = User(
                id=uuid.uuid4(),
                email=args.owner.lower(),
                full_name=args.owner.split("@")[0].replace(".", " ").title(),
                role=AppRole.ADMIN if is_first else AppRole.DELIVERY_LEAD,
            )
            users.add(owner)
            await session.flush()
            print(
                f"Created placeholder user {owner.email} "
                f"({'admin — first account' if is_first else owner.role.value})"
            )

        engagement = Engagement(
            slug=args.slug,
            name=args.name,
            client_name=args.client,
            timezone=args.timezone,
            jira_project_key=args.jira_project,
            github_repo=args.github_repo,
            morning_post_time=_parse_time(args.morning),
            eod_post_time=_parse_time(args.eod),
        )
        engagements.add(engagement)
        await session.flush()

        members.add(
            EngagementMember(
                engagement_id=engagement.id,
                user_id=owner.id,
                pod_role=PodRole.DELIVERY_LEAD,
            )
        )
        await session.flush()

        print(f"\nCreated {engagement.name} ({engagement.agent_identity})")
        print(f"  id       {engagement.id}")
        print(f"  owner    {owner.email}")
        print(f"  cadence  {engagement.morning_post_time} / {engagement.eod_post_time} "
              f"{engagement.timezone}")
        print(f"\nTry: python -m agent_pm.cli run {engagement.slug} morning_sprint_plan\n")
    return 0


async def cmd_run(args: argparse.Namespace) -> int:
    """Run one task against real data. Subject to the usual autonomy gate."""
    async with session_scope() as session:
        engagement = await EngagementRepository(session).get_by_slug(args.slug)
        if engagement is None:
            print(f"No engagement with slug {args.slug!r}.", file=sys.stderr)
            return 1

        service = EngagementService(session)
        pod = await service.get_members(engagement.id)

        outcome = await AgentRunner(session).run(
            get_task(args.task),
            engagement,
            pod,
            trigger="cli",
        )

    if outcome.skipped:
        print(f"\nSkipped: {outcome.result.skip_reason}\n")
        return 0

    print(f"\n{outcome.result.summary_markdown or '(no narrative)'}\n")
    print(f"  model              {outcome.result.model}")
    print(f"  claims             {len(outcome.result.claims)}")
    print(f"  grounding          {outcome.result.grounding_ratio}")
    print(f"  approvals created  {len(outcome.approvals)}")
    print(f"  posted to channel  {outcome.posted}")
    for note in outcome.result.notes:
        print(f"  note               {note}")
    print()
    return 0


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------


def _parse_time(value: str) -> time:
    hour, _, minute = value.partition(":")
    return time(int(hour), int(minute or 0))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-pm", description="Delivery Steward operational CLI"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("tasks", help="List the agent task catalog")
    sub.add_parser("engagements", help="List active engagements")

    seed = sub.add_parser("seed", help="Create an engagement and its first member")
    seed.add_argument("--slug", required=True, help="URL-safe id, e.g. acme-migration")
    seed.add_argument("--name", required=True, help="Display name")
    seed.add_argument("--owner", required=True, help="Email of the delivery lead")
    seed.add_argument("--client", default=None)
    seed.add_argument("--timezone", default="UTC", help="IANA name, e.g. Asia/Kolkata")
    seed.add_argument("--jira-project", default=None, dest="jira_project")
    seed.add_argument("--github-repo", default=None, dest="github_repo")
    seed.add_argument("--morning", default="08:00")
    seed.add_argument("--eod", default="17:30")

    run = sub.add_parser("run", help="Run one task for an engagement")
    run.add_argument("slug")
    run.add_argument("task", help="Task name — see `agent-pm tasks`")

    return parser


async def _dispatch(args: argparse.Namespace) -> int:
    try:
        if args.command == "engagements":
            return await cmd_engagements()
        if args.command == "seed":
            return await cmd_seed(args)
        if args.command == "run":
            return await cmd_run(args)
    finally:
        await dispose_engine()
    return 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings)

    # `tasks` reads nothing, so it stays useful when the database is down.
    if args.command == "tasks":
        return cmd_tasks()

    if not settings.database_configured:
        print(
            "DATABASE_URL is not set. Copy backend/.env.example to .env, or "
            "start the local database with `docker compose up -d postgres`.",
            file=sys.stderr,
        )
        return 2

    try:
        return asyncio.run(_dispatch(args))
    except AgentPMError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
