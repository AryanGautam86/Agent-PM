"""Task registry — the catalog from the brief, in code.

Tasks are registered by name so the scheduler, the API and the event bus all
refer to the same string. Adding a task to the catalog means adding it here;
there is no import-time scanning, because a task appearing by accident is worse
than one that has to be declared.
"""

from __future__ import annotations

from agent_pm.agents.base import AgentTask
from agent_pm.agents.tasks.action_tracking import ActionItemTrackingTask
from agent_pm.agents.tasks.blocker_risk_promotion import BlockerRiskPromotionTask
from agent_pm.agents.tasks.eod_summary import EodSummaryTask
from agent_pm.agents.tasks.meeting_intake import MeetingIntakeTask
from agent_pm.agents.tasks.morning_standup import MorningSprintPlanTask
from agent_pm.agents.tasks.raid_gap_scan import RaidGapScanTask
from agent_pm.agents.tasks.sprint_planning_prep import SprintPlanningPrepTask
from agent_pm.agents.tasks.weekly_status import WeeklyClientStatusTask
from agent_pm.core.errors import NotFoundError

TASK_TYPES: tuple[type[AgentTask], ...] = (
    MorningSprintPlanTask,
    EodSummaryTask,
    RaidGapScanTask,
    MeetingIntakeTask,
    ActionItemTrackingTask,
    BlockerRiskPromotionTask,
    WeeklyClientStatusTask,
    SprintPlanningPrepTask,
)

_TASKS: dict[str, AgentTask] = {task_type.name: task_type() for task_type in TASK_TYPES}


def get_task(name: str) -> AgentTask:
    task = _TASKS.get(name)
    if task is None:
        raise NotFoundError(
            f"Unknown agent task: {name!r}",
            details={"available": sorted(_TASKS)},
        )
    return task


def all_tasks() -> list[AgentTask]:
    return list(_TASKS.values())


def task_names() -> list[str]:
    return sorted(_TASKS)


def describe_catalog() -> list[dict[str, str | bool]]:
    """Machine-readable catalog. Surfaced by the API so the UI can render it."""
    return [
        {
            "name": task.name,
            "title": task.title,
            "description": task.description,
            "autonomy": task.autonomy.value,
            "model_tier": task.model_tier.value,
            "requires_citations": task.requires_citations,
            "posts_to_channel": task.posts_to_channel,
            "needs_approval": task.approval_kind is not None,
            "approval_kind": task.approval_kind.value if task.approval_kind else "",
        }
        for task in sorted(_TASKS.values(), key=lambda t: t.name)
    ]


__all__ = [
    "TASK_TYPES",
    "all_tasks",
    "describe_catalog",
    "get_task",
    "task_names",
]
