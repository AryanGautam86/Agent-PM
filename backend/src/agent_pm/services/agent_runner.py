"""Agent task runner.

The only component allowed to act on a :class:`TaskResult`. Tasks propose; the
runner decides. Concentrating that decision here means a new task cannot
accidentally acquire write permission by forgetting a check — it has to be
granted one by its declared autonomy level, which the engagement can lower but
never raise.

Lifecycle (see docs/ARCHITECTURE.md §3):

1. open an ``agent_runs`` row *before* any work
2. ``gather`` — read-only evidence
3. ``reason`` — the task produces a result
4. grounding validation
5. autonomy gate — approvals or direct execution
6. channel post
7. close the run row with status, model, tokens, duration

A failure at any step still closes the run row. If the transaction has to be
rolled back, the audit row is rewritten and committed on its own, because an
unexplained gap in the audit trail is worse than a partially applied change.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent_pm.agents.base import AgentTask
from agent_pm.agents.context import EngagementContext, MemberContext, TaskContext
from agent_pm.agents.results import ProposedWrite, TaskResult
from agent_pm.core.clock import local_today, utc_now
from agent_pm.core.config import Settings, get_settings
from agent_pm.core.enums import ApprovalStatus, AutonomyLevel, RunStatus
from agent_pm.core.errors import AgentPMError, AutonomyViolationError
from agent_pm.core.grounding import GroundingPolicy
from agent_pm.core.logging import get_logger
from agent_pm.integrations.registry import IntegrationRegistry, get_registry
from agent_pm.models.approval import Approval
from agent_pm.models.engagement import Engagement
from agent_pm.models.run import AgentRun
from agent_pm.models.user import EngagementMember

logger = get_logger(__name__)


@dataclass(slots=True)
class RunOutcome:
    run: AgentRun
    result: TaskResult
    approvals: list[Approval] = field(default_factory=list)
    posted: bool = False

    @property
    def skipped(self) -> bool:
        return self.result.skipped


def build_engagement_context(
    engagement: Engagement, members: Sequence[EngagementMember]
) -> EngagementContext:
    """Flatten ORM rows into the immutable snapshot a task receives."""
    return EngagementContext(
        id=engagement.id,
        slug=engagement.slug,
        name=engagement.name,
        client_name=engagement.client_name,
        timezone=engagement.timezone,
        jira_project_key=engagement.jira_project_key,
        jira_board_id=engagement.jira_board_id,
        github_repo=engagement.github_repo,
        raid_workbook_url=engagement.raid_workbook_url,
        channel_target=engagement.teams_webhook_url or engagement.teams_channel_id,
        autonomy_ceiling=engagement.autonomy_ceiling,
        members=[
            MemberContext(
                user_id=member.user_id,
                display_name=member.user.display_name if member.user else "Unknown",
                email=member.user.email if member.user else None,
                pod_role=member.pod_role,
                jira_account_id=member.jira_account_id,
                github_login=member.github_login,
                capacity_hours_per_sprint=member.capacity_hours_per_sprint,
                nudges_enabled=member.nudges_enabled,
            )
            for member in members
        ],
    )


class AgentRunner:
    def __init__(
        self,
        session: AsyncSession,
        *,
        registry: IntegrationRegistry | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.registry = registry or get_registry()
        self.grounding = GroundingPolicy(self.settings.grounding_min_citation_ratio)

    async def run(
        self,
        task: AgentTask,
        engagement: Engagement,
        members: Sequence[EngagementMember],
        *,
        trigger: str = "api",
        for_date: date | None = None,
        prior: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        triggered_by_user_id: uuid.UUID | None = None,
    ) -> RunOutcome:
        autonomy = engagement.effective_autonomy(task.autonomy)
        target_date = for_date or local_today(engagement.timezone)
        started = utc_now()
        clock_start = time.perf_counter()

        run = AgentRun(
            engagement_id=engagement.id,
            task_name=task.name,
            trigger=trigger,
            triggered_by_user_id=triggered_by_user_id,
            status=RunStatus.RUNNING,
            autonomy_level=autonomy,
            model_tier=task.model_tier,
            started_at=started,
        )
        self.session.add(run)
        await self.session.flush()  # the run id is needed by any approval rows

        context = TaskContext(
            engagement=build_engagement_context(engagement, members),
            registry=self.registry,
            for_date=target_date,
            trigger=trigger,
            triggered_by_user_id=triggered_by_user_id,
            prior=prior or {},
            params=params or {},
        )

        try:
            evidence = await task.gather(context)
            result = await task.reason(context, evidence)
        except Exception as exc:
            await self._record_failure(run, exc, started, clock_start)
            raise

        if result.skipped:
            run.status = RunStatus.SKIPPED
            run.output_summary = {"skip_reason": result.skip_reason}
            run.finished_at = utc_now()
            run.duration_ms = int((time.perf_counter() - clock_start) * 1000)
            logger.info(
                "agent_task_skipped",
                extra={"task": task.name, "reason": result.skip_reason},
            )
            return RunOutcome(run=run, result=result)

        try:
            self._validate_grounding(task, result)
            approvals = self._gate_writes(task, engagement, run, autonomy, result)
            posted = await self._post_card(task, context, autonomy, result)
        except Exception as exc:
            await self._record_failure(run, exc, started, clock_start)
            raise

        run.status = RunStatus.SUCCESS
        run.model = result.model
        run.grounding_ratio = result.grounding_ratio
        run.input_tokens = result.input_tokens
        run.output_tokens = result.output_tokens
        run.finished_at = utc_now()
        run.duration_ms = int((time.perf_counter() - clock_start) * 1000)
        run.input_digest = {
            "evidence_count": len(result.evidence),
            "for_date": target_date.isoformat(),
            "integrations": self.registry.describe(),
        }
        run.output_summary = {
            "claims": len(result.claims),
            "approvals_created": len(approvals),
            "posted": posted,
            "notes": result.notes,
        }

        logger.info(
            "agent_task_completed",
            extra={
                "task": task.name,
                "engagement": engagement.slug,
                "autonomy": autonomy.value,
                "approvals": len(approvals),
                "posted": posted,
                "grounding_ratio": result.grounding_ratio,
            },
        )
        return RunOutcome(run=run, result=result, approvals=approvals, posted=posted)

    # ---- steps -----------------------------------------------------------

    def _validate_grounding(self, task: AgentTask, result: TaskResult) -> None:
        if not task.requires_citations:
            return
        report = self.grounding.validate(result.claims, result.evidence)
        result.grounding_ratio = report.ratio

    def _gate_writes(
        self,
        task: AgentTask,
        engagement: Engagement,
        run: AgentRun,
        autonomy: AutonomyLevel,
        result: TaskResult,
    ) -> list[Approval]:
        """Turn proposed writes into approvals, or let them through.

        A write executes without an approval only when the task explicitly
        opts in *and* its effective level permits external action. Everything
        touching Jira or the RAID log opts out, so those always queue.
        """
        if not result.proposed_writes:
            return []

        if task.auto_execute_writes:
            if not autonomy.may_write_externally:
                raise AutonomyViolationError(
                    f"Task {task.name!r} wants to write at autonomy "
                    f"{autonomy.value}, which does not permit external action",
                    details={"task": task.name, "autonomy": autonomy.value},
                )
            return []  # caller executes; nothing to approve

        expires_at = utc_now() + timedelta(hours=self.settings.approval_expiry_hours)
        approvals = [
            self._to_approval(engagement, run, task, proposal, expires_at)
            for proposal in result.proposed_writes
        ]
        self.session.add_all(approvals)
        return approvals

    @staticmethod
    def _to_approval(
        engagement: Engagement,
        run: AgentRun,
        task: AgentTask,
        proposal: ProposedWrite,
        expires_at: Any,
    ) -> Approval:
        return Approval(
            engagement_id=engagement.id,
            kind=proposal.kind,
            status=ApprovalStatus.PENDING,
            title=proposal.title,
            rationale=proposal.rationale,
            payload=proposal.payload,
            citations=proposal.citation_dicts(),
            requested_by_task=task.name,
            agent_run_id=run.id,
            expires_at=expires_at,
        )

    async def _post_card(
        self,
        task: AgentTask,
        context: TaskContext,
        autonomy: AutonomyLevel,
        result: TaskResult,
    ) -> bool:
        if result.card is None or not task.posts_to_channel:
            return False
        if not autonomy.may_write_externally:
            # L1/L2: the card stays in the app for a human to look at.
            result.notes.append(
                f"Card withheld: autonomy {autonomy.value} does not permit posting."
            )
            return False
        if context.param("post_to_channel") is False:
            result.notes.append("Card withheld: caller opted out.")
            return False

        target = context.engagement.channel_target or ""
        try:
            await self.registry.channel.post_card(target, result.card)
        except AgentPMError as exc:
            # A channel failure must not fail the run: the post is a delivery
            # mechanism, the standup row is the record.
            logger.warning(
                "channel_post_failed", extra={"task": task.name, "error": str(exc)}
            )
            result.notes.append(f"Channel post failed: {exc.message}")
            return False
        return True

    async def _record_failure(
        self,
        run: AgentRun,
        exc: Exception,
        started: Any,
        clock_start: float,
    ) -> None:
        """Persist the failure even though the transaction is being abandoned.

        Rolls back whatever partial work exists, then writes a standalone audit
        row and commits it. Without this, a task that fails halfway leaves no
        trace of having run at all.
        """
        code = exc.code if isinstance(exc, AgentPMError) else type(exc).__name__
        logger.exception(
            "agent_task_failed", extra={"task": run.task_name, "error_code": code}
        )

        await self.session.rollback()

        failure = AgentRun(
            engagement_id=run.engagement_id,
            task_name=run.task_name,
            trigger=run.trigger,
            triggered_by_user_id=run.triggered_by_user_id,
            status=RunStatus.FAILED,
            autonomy_level=run.autonomy_level,
            model_tier=run.model_tier,
            started_at=started,
            finished_at=utc_now(),
            duration_ms=int((time.perf_counter() - clock_start) * 1000),
            error_code=str(code),
            error=str(exc)[:4000],
        )
        self.session.add(failure)
        await self.session.commit()
