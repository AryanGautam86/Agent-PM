from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from agent_pm.api.deps import CurrentUserDep, DbSession, PaginationDep
from agent_pm.core.enums import ReportKind
from agent_pm.schemas.report import ReportGenerateRequest, ReportRead, ReportUpdate
from agent_pm.services.report_service import ReportService

router = APIRouter(prefix="/engagements/{engagement_id}/reports", tags=["reports"])


@router.get("", response_model=list[ReportRead], summary="List reports")
async def list_reports(
    engagement_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSession,
    page: PaginationDep,
    kind: ReportKind | None = Query(default=None),
) -> list[ReportRead]:
    reports = await ReportService(session).list_items(
        engagement_id, user, kind=kind, limit=page.limit, offset=page.offset
    )
    return [ReportRead.model_validate(report) for report in reports]


@router.get("/{report_id}", response_model=ReportRead, summary="Get one report")
async def get_report(
    engagement_id: uuid.UUID,
    report_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSession,
) -> ReportRead:
    report = await ReportService(session).get(engagement_id, report_id, user)
    return ReportRead.model_validate(report)


@router.post(
    "/weekly-status",
    response_model=ReportRead,
    summary="Generate the weekly client status",
)
async def generate_weekly_status(
    engagement_id: uuid.UUID,
    payload: ReportGenerateRequest,
    user: CurrentUserDep,
    session: DbSession,
) -> ReportRead:
    """Routes to the narrative model and creates an approval for the lead."""
    report = await ReportService(session).generate(
        engagement_id, ReportKind.WEEKLY_STATUS, payload, user
    )
    return ReportRead.model_validate(report)


@router.post(
    "/planning-pack",
    response_model=ReportRead,
    summary="Generate the sprint planning pack",
)
async def generate_planning_pack(
    engagement_id: uuid.UUID,
    payload: ReportGenerateRequest,
    user: CurrentUserDep,
    session: DbSession,
) -> ReportRead:
    report = await ReportService(session).generate(
        engagement_id, ReportKind.SPRINT_PLANNING_PACK, payload, user
    )
    return ReportRead.model_validate(report)


@router.patch("/{report_id}", response_model=ReportRead, summary="Edit a report")
async def update_report(
    engagement_id: uuid.UUID,
    report_id: uuid.UUID,
    payload: ReportUpdate,
    user: CurrentUserDep,
    session: DbSession,
) -> ReportRead:
    report = await ReportService(session).update(engagement_id, report_id, payload, user)
    return ReportRead.model_validate(report)


@router.post("/{report_id}/sent", response_model=ReportRead, summary="Mark as sent")
async def mark_sent(
    engagement_id: uuid.UUID,
    report_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSession,
) -> ReportRead:
    report = await ReportService(session).mark_sent(engagement_id, report_id, user)
    return ReportRead.model_validate(report)
