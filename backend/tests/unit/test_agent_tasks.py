"""Agent tasks against fixture integrations.

No database, no network. Each test asserts on the structured artifact rather
than on prose, because the prose is the model's and the structure is ours.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from agent_pm.agents.context import TaskContext
from agent_pm.agents.registry import get_task
from agent_pm.agents.tasks.action_tracking import ActionItemView
from agent_pm.core.clock import utc_now
from agent_pm.core.enums import ApprovalKind
from agent_pm.core.grounding import GroundingPolicy


async def run(task_name: str, ctx: TaskContext):
    task = get_task(task_name)
    evidence = await task.gather(ctx)
    return task, await task.reason(ctx, evidence)


# ---------------------------------------------------------------- standups


async def test_morning_plan_counts_come_from_jira_not_the_model(
    task_context: TaskContext,
) -> None:
    _, result = await run("morning_sprint_plan", task_context)

    per_person = result.artifact["per_person"]
    assert len(per_person) == 4

    for person in per_person:
        # The invariant the model cannot break, because it never produces it.
        assert person["committed"] == person["delivered"] + person["pending"]

    assert result.artifact["metrics"]["issues"] == 12


async def test_morning_plan_output_is_grounded(task_context: TaskContext) -> None:
    task, result = await run("morning_sprint_plan", task_context)

    assert task.requires_citations
    report = GroundingPolicy(0.9).validate(result.claims, result.evidence)
    assert report.passed


async def test_morning_plan_surfaces_blockers_with_ages(
    task_context: TaskContext,
) -> None:
    _, result = await run("morning_sprint_plan", task_context)

    blockers = result.artifact["blockers"]
    assert len(blockers) == 3
    # Oldest first — the PO reads the top of the list.
    ages = [entry["age_days"] for entry in blockers]
    assert ages == sorted(ages, reverse=True)


async def test_morning_plan_posts_a_card(task_context: TaskContext) -> None:
    _, result = await run("morning_sprint_plan", task_context)
    assert result.card is not None
    assert "Morning sprint plan" in result.card.title


async def test_eod_summary_includes_the_engineering_signal(
    task_context: TaskContext,
) -> None:
    _, result = await run("eod_summary", task_context)

    assert result.artifact["highlights"], "commits should appear as highlights"
    # Commit shas are part of the evidence set, so they are citable.
    kinds = {citation.kind for citation in result.evidence}
    assert "commit" in kinds


# --------------------------------------------------------------- gap scan


async def test_gap_scan_proposes_only_uncovered_blockers(
    task_context: TaskContext,
) -> None:
    """The fixture RAID log covers DEMO-111; two other blockers are missing."""
    _, result = await run("raid_gap_scan", task_context)

    assert result.artifact["checked"] == 3
    assert result.artifact["gap_count"] == len(result.proposed_writes)

    gap_keys = set(result.artifact["gap_keys"])
    proposed = {write.payload["source_ref"] for write in result.proposed_writes}
    assert proposed == gap_keys
    assert "DEMO-111" not in proposed, "already covered by the fixture workbook"


async def test_gap_scan_writes_nothing_itself(task_context: TaskContext) -> None:
    """Proposals only. The RAID workbook must be untouched by the scan."""
    storage = task_context.registry.storage
    before = await storage.read_raid_rows("memory://raid.xlsx")

    _, result = await run("raid_gap_scan", task_context)

    after = await storage.read_raid_rows("memory://raid.xlsx")
    assert len(after) == len(before)
    assert result.proposed_writes
    assert all(
        write.kind is ApprovalKind.RAID_GAP_ADD for write in result.proposed_writes
    )


async def test_gap_scan_skips_refs_already_known_to_the_database(
    task_context: TaskContext,
) -> None:
    """`prior.raid_source_refs` is how the service reports what it already has."""
    _, baseline = await run("raid_gap_scan", task_context)
    covered = list(baseline.artifact["gap_keys"])

    ctx = replace(task_context, prior={"raid_source_refs": covered})
    _, result = await run("raid_gap_scan", ctx)

    assert result.artifact["gap_count"] == 0
    assert result.proposed_writes == []


# -------------------------------------------------------- risk promotion


async def test_risk_promotion_respects_the_age_threshold(
    task_context: TaskContext,
) -> None:
    ctx = replace(task_context, params={"age_threshold_days": 2})
    _, result = await run("blocker_risk_promotion", ctx)

    # Fixture blockers are aged 4, 1 and 3 days: two qualify.
    assert len(result.artifact["candidate_keys"]) == 2


async def test_risk_promotion_skips_when_nothing_has_aged(
    task_context: TaskContext,
) -> None:
    ctx = replace(task_context, params={"age_threshold_days": 30})
    _, result = await run("blocker_risk_promotion", ctx)

    assert result.skipped
    assert result.proposed_writes == []


# ------------------------------------------------------- action tracking


def _view(**overrides) -> ActionItemView:
    base = {
        "id": "00000000-0000-0000-0000-000000000001",
        "title": "Send the vendor contract",
        "owner_label": "Priya Nair",
        "owner_user_id": "user-1",
        "owner_email": "priya@example.com",
        "due_at": utc_now() + timedelta(hours=6),
    }
    return ActionItemView.model_validate({**base, **overrides})


async def test_nudges_items_due_within_the_lead_time(
    task_context: TaskContext,
) -> None:
    ctx = replace(
        task_context,
        prior={"open_items": [_view()], "nudges_today": {}},
        params={"nudge_lead_time_hours": 24, "max_nudges_per_person_per_day": 3},
    )
    _, result = await run("action_item_tracking", ctx)

    assert len(result.artifact["nudges"]) == 1
    assert result.artifact["escalations"] == []


async def test_does_not_nudge_items_that_are_not_due_soon(
    task_context: TaskContext,
) -> None:
    ctx = replace(
        task_context,
        prior={
            "open_items": [_view(due_at=utc_now() + timedelta(days=9))],
            "nudges_today": {},
        },
        params={"nudge_lead_time_hours": 24},
    )
    _, result = await run("action_item_tracking", ctx)

    assert result.skipped


async def test_escalates_overdue_items_once(task_context: TaskContext) -> None:
    overdue = _view(due_at=utc_now() - timedelta(hours=30))
    already = _view(
        id="00000000-0000-0000-0000-000000000002",
        due_at=utc_now() - timedelta(hours=30),
        escalated_at=utc_now() - timedelta(hours=2),
    )

    ctx = replace(
        task_context,
        prior={"open_items": [overdue, already], "nudges_today": {}},
    )
    _, result = await run("action_item_tracking", ctx)

    assert len(result.artifact["escalations"]) == 1
    assert result.artifact["escalations"][0]["id"] == overdue.id


async def test_daily_cap_suppresses_further_nudges(
    task_context: TaskContext,
) -> None:
    """Notification fatigue is a named risk in the brief."""
    ctx = replace(
        task_context,
        prior={"open_items": [_view()], "nudges_today": {"user-1": 3}},
        params={"nudge_lead_time_hours": 24, "max_nudges_per_person_per_day": 3},
    )
    _, result = await run("action_item_tracking", ctx)

    assert result.artifact["nudges"] == []
    assert result.artifact["suppressed_by_cap"] == ["Send the vendor contract"]


async def test_muted_items_are_never_nudged(task_context: TaskContext) -> None:
    ctx = replace(
        task_context,
        prior={"open_items": [_view(nudges_muted=True)], "nudges_today": {}},
    )
    _, result = await run("action_item_tracking", ctx)

    assert result.skipped


# --------------------------------------------------------- meeting intake


async def test_meeting_intake_ignores_tickets_outside_the_sprint(
    task_context: TaskContext,
) -> None:
    """A hallucinated ticket key must not become a Jira comment."""
    ctx = replace(
        task_context,
        prior={
            "meeting_outcome": {
                "meeting_id": "meet-1",
                "title": "Sprint review",
                "decisions": [
                    {"text": "Ship OTP first", "owner": "Priya", "timestamp": "00:04:11"}
                ],
                "actions": [
                    {
                        "text": "Confirm the vendor SSO date",
                        "owner": "Daniel",
                        "due": "2026-08-08",
                        "timestamp": "00:12:03",
                    }
                ],
                "risks": [{"text": "Vendor may slip", "timestamp": "00:15:40"}],
            }
        },
    )
    _, result = await run("meeting_outcome_intake", ctx)

    assert result.artifact["action_items"], "the action item should be captured"
    for write in result.proposed_writes:
        if write.kind is ApprovalKind.JIRA_UPDATE:
            assert write.payload["issue_key"].startswith("DEMO-")


async def test_meeting_intake_skips_an_empty_envelope(
    task_context: TaskContext,
) -> None:
    ctx = replace(task_context, prior={"meeting_outcome": {"meeting_id": "meet-2"}})
    _, result = await run("meeting_outcome_intake", ctx)

    assert result.skipped


# ------------------------------------------------------------------ misc


@pytest.mark.parametrize(
    "task_name",
    [
        "morning_sprint_plan",
        "eod_summary",
        "raid_gap_scan",
        "blocker_risk_promotion",
        "weekly_client_status",
        "sprint_planning_prep",
    ],
)
async def test_every_llm_task_records_which_model_ran(
    task_name: str, task_context: TaskContext
) -> None:
    _, result = await run(task_name, task_context)
    if not result.skipped:
        assert result.model, f"{task_name} should record its model for the audit"


async def test_weekly_status_uses_the_narrative_model_tier(
    task_context: TaskContext,
) -> None:
    task, result = await run("weekly_client_status", task_context)

    assert task.model_tier.value == "narrative"
    expected = task_context.registry.model_for(task.model_tier)
    assert expected in (result.model or "")


async def test_sprint_planning_reports_carryover(task_context: TaskContext) -> None:
    _, result = await run("sprint_planning_prep", task_context)

    sections = result.artifact["sections"]
    assert sections["carryover_count"] == 9  # 12 fixture issues, 3 done
    assert sections["velocity_average"] > 0


def test_fixture_clock_helpers_are_timezone_aware() -> None:
    assert isinstance(utc_now(), datetime)
    assert utc_now().tzinfo is not None
