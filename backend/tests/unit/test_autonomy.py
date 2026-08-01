"""Autonomy levels and the engagement ceiling.

The rule the brief cares about: no task may write to an external system
without a human, and an engagement can be more conservative than a task
declares but never more permissive.
"""

from __future__ import annotations

from datetime import time

import pytest

from agent_pm.agents.registry import all_tasks, get_task
from agent_pm.core.enums import AutonomyLevel
from agent_pm.core.errors import NotFoundError
from agent_pm.models.engagement import Engagement


def make_engagement(ceiling: AutonomyLevel) -> Engagement:
    return Engagement(
        slug="demo",
        name="Demo",
        timezone="UTC",
        morning_post_time=time(8, 0),
        eod_post_time=time(17, 30),
        autonomy_ceiling=ceiling,
        task_overrides={},
    )


@pytest.mark.parametrize(
    ("level", "may_write"),
    [
        (AutonomyLevel.L1_SUGGEST, False),
        (AutonomyLevel.L2_DRAFT_APPROVE, False),
        (AutonomyLevel.L3_ACT_REVIEW, True),
        (AutonomyLevel.L4_AUTONOMOUS, True),
    ],
)
def test_only_l3_and_above_may_act_externally(
    level: AutonomyLevel, may_write: bool
) -> None:
    assert level.may_write_externally is may_write


def test_ceiling_lowers_a_task_level() -> None:
    engagement = make_engagement(AutonomyLevel.L2_DRAFT_APPROVE)
    effective = engagement.effective_autonomy(AutonomyLevel.L4_AUTONOMOUS)

    assert effective is AutonomyLevel.L2_DRAFT_APPROVE
    assert not effective.may_write_externally


def test_ceiling_never_raises_a_task_level() -> None:
    engagement = make_engagement(AutonomyLevel.L4_AUTONOMOUS)
    effective = engagement.effective_autonomy(AutonomyLevel.L1_SUGGEST)

    assert effective is AutonomyLevel.L1_SUGGEST


def test_task_overrides_can_disable_a_task() -> None:
    engagement = make_engagement(AutonomyLevel.L3_ACT_REVIEW)
    engagement.task_overrides = {"eod_summary": {"enabled": False}}

    assert engagement.task_enabled("morning_sprint_plan")
    assert not engagement.task_enabled("eod_summary")


def test_agent_identity_is_derived_from_the_slug() -> None:
    assert make_engagement(AutonomyLevel.L3_ACT_REVIEW).agent_identity == "agent-pm-demo"


def test_no_task_that_writes_to_a_client_system_auto_executes() -> None:
    """The brief's hard rule, asserted across the whole catalog.

    Only the nudge task may act without an approval, because a direct message
    is not a system of record.
    """
    auto = {task.name for task in all_tasks() if task.auto_execute_writes}
    assert auto == {"action_item_tracking"}


def test_every_task_declaring_an_approval_kind_requires_approval() -> None:
    for task in all_tasks():
        if task.approval_kind is not None:
            assert not task.auto_execute_writes, task.name


def test_unknown_task_name_is_rejected() -> None:
    with pytest.raises(NotFoundError):
        get_task("no_such_task")
