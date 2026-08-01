"""Sprint planning prep.

Brief: *24h before planning, post velocity, carryover, capacity, proposed
backlog slice.* Autonomy L2 — PO and Tech Lead validate before planning.

The proposed slice is sized against measured velocity and declared capacity,
not against optimism. Where the two disagree the task reports the gap rather
than splitting the difference.
"""

from __future__ import annotations

from typing import Any

from agent_pm.agents.base import AgentTask
from agent_pm.agents.context import TaskContext
from agent_pm.agents.prompts import narrative_schema
from agent_pm.agents.results import TaskResult
from agent_pm.core.enums import ApprovalKind, AutonomyLevel, ModelTier
from agent_pm.core.logging import get_logger

logger = get_logger(__name__)

INSTRUCTIONS = """\
Prepare the pack the pod will use in sprint planning.

Cover:
1. **Velocity** — the measured average, and whether the last sprint was typical.
2. **Carryover** — what is not finishing this sprint and must be re-planned.
   Name it; carryover that is not named gets forgotten.
3. **Capacity** — declared capacity for the coming sprint, and how it compares
   with velocity. If capacity is materially below velocity, lead with that.
4. **Proposed slice** — the items you would commit to, and the point total.
   Stay at or under the lower of velocity and capacity. State explicitly what
   you left out and why.

If the backlog is not refined enough to propose a slice, say so instead of
proposing one.
"""

PLANNING_SCHEMA = narrative_schema(
    {
        "proposed_points": {"type": "number"},
        "proposed_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["issue_key", "reason"],
            },
        },
        "deferred_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue_key": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["issue_key", "reason"],
            },
        },
    }
)


class SprintPlanningPrepTask(AgentTask):
    name = "sprint_planning_prep"
    title = "Sprint planning prep"
    description = (
        "Post velocity, carryover, capacity and a proposed backlog slice "
        "before sprint planning."
    )

    autonomy = AutonomyLevel.L2_DRAFT_APPROVE
    model_tier = ModelTier.STRUCTURED
    approval_kind = ApprovalKind.SPRINT_PLAN
    posts_to_channel = False
    auto_execute_writes = False

    def instructions(self) -> str:
        return INSTRUCTIONS

    async def gather(self, ctx: TaskContext) -> dict[str, Any]:
        project_key = ctx.engagement.jira_project_key or ctx.engagement.slug.upper()
        snapshot = await ctx.registry.jira.get_sprint_snapshot(
            project_key, board_id=ctx.engagement.jira_board_id
        )
        velocity = await ctx.registry.jira.get_velocity(project_key)

        capacity = sum(
            member.capacity_hours_per_sprint or 0 for member in ctx.engagement.members
        )
        return {"snapshot": snapshot, "velocity": velocity, "capacity_hours": capacity}

    async def reason(self, ctx: TaskContext, evidence: dict[str, Any]) -> TaskResult:
        snapshot = evidence["snapshot"]
        velocity = evidence["velocity"]
        capacity_hours: int = evidence["capacity_hours"]

        carryover = snapshot.pending
        carryover_points = sum(issue.story_points or 0.0 for issue in carryover)

        lines = [
            f"Average velocity: {velocity.average:.1f} points",
            f"Declared capacity: {capacity_hours} hours across "
            f"{len(ctx.engagement.members)} people"
            + (" (not configured)" if capacity_hours == 0 else ""),
            f"Carryover: {len(carryover)} items, {carryover_points:g} points",
        ]
        lines += [
            f"CARRYOVER {issue.key} — {issue.summary} | {issue.status} | "
            f"{issue.story_points or 0:g} pts | owner {issue.owner}"
            for issue in carryover
        ]
        lines += [
            f"velocity history: {entry.get('sprint')} = {entry.get('points')} pts"
            for entry in velocity.sprint_points
        ]

        prompt = self.build_user_prompt(
            instruction="Prepare the sprint planning pack.",
            evidence_lines=lines,
            citations=snapshot.citations(),
        )

        response = await self.ask_json(
            ctx, prompt=prompt, schema=PLANNING_SCHEMA, schema_name="planning_pack"
        )
        data = response.data
        content = str(data.get("summary_markdown", "")).strip()

        return TaskResult(
            task_name=self.name,
            claims=self.parse_claims(data.get("claims")),
            evidence=snapshot.citations(),
            artifact={
                "title": f"{ctx.engagement.name} — sprint planning pack",
                "content_markdown": content,
                "sections": {
                    "velocity_average": velocity.average,
                    "capacity_hours": capacity_hours,
                    "carryover_count": len(carryover),
                    "carryover_points": carryover_points,
                    "proposed_points": data.get("proposed_points", 0),
                    "proposed_items": data.get("proposed_items", []),
                    "deferred_items": data.get("deferred_items", []),
                },
            },
            summary_markdown=content,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
