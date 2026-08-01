"""Evaluation harness.

    python -m agent_pm.evals.runner              # every case
    python -m agent_pm.evals.runner morning-001  # one case

Runs tasks against fixture integrations, with no database. Exit code 1 when the
suite falls below the pass threshold, so it works as a CI gate.

With no ``ANTHROPIC_API_KEY`` the fixture model runs, which makes this a
structural check — wiring, schemas, grounding plumbing. With a key set, it
becomes a real quality gate against the configured models.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass, field

from agent_pm.agents.context import EngagementContext, MemberContext, TaskContext
from agent_pm.agents.registry import get_task
from agent_pm.agents.results import TaskResult
from agent_pm.core.clock import local_today
from agent_pm.core.config import get_settings
from agent_pm.core.enums import PodRole
from agent_pm.core.logging import configure_logging, get_logger
from agent_pm.evals.cases import CASES, EvalCase
from agent_pm.integrations.registry import IntegrationRegistry

logger = get_logger(__name__)

PASS_THRESHOLD = 0.9


@dataclass(slots=True)
class CaseReport:
    case_id: str
    task_name: str
    passed: bool
    score: float
    failures: list[str] = field(default_factory=list)
    error: str | None = None


def _demo_context(registry: IntegrationRegistry, case: EvalCase) -> TaskContext:
    engagement = EngagementContext(
        id=uuid.uuid4(),
        slug="eval-pod",
        name="Eval Pod",
        client_name="Example Client",
        timezone="UTC",
        jira_project_key="DEMO",
        github_repo="example/demo",
        raid_workbook_url="memory://raid.xlsx",
        members=[
            MemberContext(display_name="Priya Nair", pod_role=PodRole.PRODUCT_OWNER),
            MemberContext(display_name="Daniel Okafor", pod_role=PodRole.TECH_LEAD),
            MemberContext(display_name="Mei Lin"),
            MemberContext(display_name="Tomas Vidal"),
        ],
    )
    return TaskContext(
        engagement=engagement,
        registry=registry,
        for_date=local_today("UTC"),
        trigger="eval",
        prior=dict(case.prior),
        params=dict(case.params),
    )


def _score(case: EvalCase, result: TaskResult) -> CaseReport:
    total = sum(assertion.weight for assertion in case.assertions) or 1.0
    earned = 0.0
    failures: list[str] = []
    critical_failed = False

    for assertion in case.assertions:
        try:
            ok = assertion.check(result)
        except Exception as exc:
            ok = False
            failures.append(f"{assertion.name} raised {type(exc).__name__}: {exc}")
        if ok:
            earned += assertion.weight
        else:
            if assertion.name not in " ".join(failures):
                failures.append(assertion.name)
            if assertion.critical:
                critical_failed = True

    score = earned / total
    return CaseReport(
        case_id=case.id,
        task_name=case.task_name,
        passed=score >= PASS_THRESHOLD and not critical_failed,
        score=score,
        failures=failures,
    )


async def run_case(case: EvalCase, registry: IntegrationRegistry) -> CaseReport:
    task = get_task(case.task_name)
    context = _demo_context(registry, case)
    try:
        evidence = await task.gather(context)
        result = await task.reason(context, evidence)
    except Exception as exc:
        return CaseReport(
            case_id=case.id,
            task_name=case.task_name,
            passed=False,
            score=0.0,
            error=f"{type(exc).__name__}: {exc}",
        )

    if result.skipped:
        return CaseReport(
            case_id=case.id,
            task_name=case.task_name,
            passed=False,
            score=0.0,
            error=f"Task skipped: {result.skip_reason}",
        )

    return _score(case, result)


async def run_suite(case_ids: list[str] | None = None) -> list[CaseReport]:
    registry = IntegrationRegistry()
    selected = [case for case in CASES if not case_ids or case.id in case_ids]
    if not selected:
        raise SystemExit(f"No matching cases. Available: {[c.id for c in CASES]}")

    try:
        return [await run_case(case, registry) for case in selected]
    finally:
        await registry.aclose()


def main() -> int:
    settings = get_settings()
    configure_logging(settings)

    reports = asyncio.run(run_suite(sys.argv[1:] or None))

    print(f"\nEval suite — {len(reports)} case(s)")
    print(f"Model: {'live' if settings.anthropic_configured else 'fixture'}\n")

    for report in reports:
        mark = "PASS" if report.passed else "FAIL"
        print(f"  [{mark}] {report.case_id:<22} {report.score:>6.1%}  {report.task_name}")
        if report.error:
            print(f"         error: {report.error}")
        for failure in report.failures:
            print(f"         failed: {failure}")

    passed = sum(1 for report in reports if report.passed)
    rate = passed / len(reports)
    print(f"\n{passed}/{len(reports)} passed ({rate:.0%})\n")
    return 0 if rate >= PASS_THRESHOLD else 1


if __name__ == "__main__":
    raise SystemExit(main())
