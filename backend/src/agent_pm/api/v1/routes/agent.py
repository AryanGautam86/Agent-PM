"""Task catalog and the run audit trail."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from agent_pm.agents.registry import describe_catalog, get_task
from agent_pm.api.deps import CurrentUserDep, DbSession, EditorUserDep, PaginationDep
from agent_pm.core.enums import RunStatus
from agent_pm.repositories.run import AgentRunRepository
from agent_pm.schemas.agent import (
    AgentRunRead,
    TaskCatalogEntry,
    TaskRunRequest,
    TaskRunResponse,
)
from agent_pm.services.agent_runner import AgentRunner
from agent_pm.services.engagement_service import EngagementService

router = APIRouter(tags=["agent"])


@router.get(
    "/agent/tasks",
    response_model=list[TaskCatalogEntry],
    summary="The task catalog",
)
async def list_tasks(_: CurrentUserDep) -> list[TaskCatalogEntry]:
    """Every task, with its autonomy level and whether it needs approval.

    The UI renders this rather than hard-coding the catalog, so a new task
    appears in the app the moment it is registered.
    """
    return [TaskCatalogEntry.model_validate(entry) for entry in describe_catalog()]


@router.get(
    "/engagements/{engagement_id}/agent/runs",
    response_model=list[AgentRunRead],
    summary="Agent run history",
)
async def list_runs(
    engagement_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSession,
    page: PaginationDep,
    task_name: str | None = Query(default=None),
    run_status: RunStatus | None = Query(default=None, alias="status"),
) -> list[AgentRunRead]:
    await EngagementService(session).require_access(engagement_id, user)
    runs = await AgentRunRepository(session).list_for_engagement(
        engagement_id,
        task_name=task_name,
        status=run_status,
        limit=page.limit,
        offset=page.offset,
    )
    return [AgentRunRead.model_validate(run) for run in runs]


@router.post(
    "/engagements/{engagement_id}/agent/tasks/{task_name}/run",
    response_model=TaskRunResponse,
    summary="Run a catalog task now",
)
async def run_task(
    engagement_id: uuid.UUID,
    task_name: str,
    payload: TaskRunRequest,
    user: EditorUserDep,
    session: DbSession,
) -> TaskRunResponse:
    """Manual invocation, for testing a task's behaviour on real data.

    The autonomy gate still applies: running a task by hand does not grant it
    permission it would not have on a schedule. Tasks whose results need
    domain-specific persistence (standups, reports) have their own endpoints —
    this one runs the task and records the audit row without wiring the result
    into a domain table.
    """
    service = EngagementService(session)
    engagement = await service.require_access(engagement_id, user)
    members = await service.get_members(engagement_id)

    outcome = await AgentRunner(session).run(
        get_task(task_name),
        engagement,
        members,
        trigger="api",
        for_date=payload.for_date,
        params=payload.params,
        triggered_by_user_id=user.id,
    )

    return TaskRunResponse(
        run=AgentRunRead.model_validate(outcome.run),
        skipped=outcome.skipped,
        skip_reason=outcome.result.skip_reason,
        summary_markdown=outcome.result.summary_markdown,
        approvals_created=len(outcome.approvals),
        posted=outcome.posted,
        notes=outcome.result.notes,
    )
