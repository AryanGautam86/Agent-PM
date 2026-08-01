"""The HITL surface.

This is where a human decides, and the only path by which the agent's proposals
reach Jira or the RAID log.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from agent_pm.api.deps import CurrentUserDep, DbSession, PaginationDep
from agent_pm.core.enums import ApprovalKind, ApprovalStatus
from agent_pm.schemas.approval import (
    ApprovalDecision,
    ApprovalDecisionResult,
    ApprovalRead,
    BulkApprovalDecision,
    BulkApprovalResult,
)
from agent_pm.services.approval_service import ApprovalService

router = APIRouter(prefix="/engagements/{engagement_id}/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalRead], summary="List approvals")
async def list_approvals(
    engagement_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSession,
    page: PaginationDep,
    approval_status: ApprovalStatus | None = Query(default=None, alias="status"),
    kind: ApprovalKind | None = Query(default=None),
) -> list[ApprovalRead]:
    approvals = await ApprovalService(session).list_items(
        engagement_id,
        user,
        status=approval_status,
        kind=kind,
        limit=page.limit,
        offset=page.offset,
    )
    return [ApprovalRead.model_validate(approval) for approval in approvals]


@router.get("/{approval_id}", response_model=ApprovalRead, summary="Get one approval")
async def get_approval(
    engagement_id: uuid.UUID,
    approval_id: uuid.UUID,
    user: CurrentUserDep,
    session: DbSession,
) -> ApprovalRead:
    approval = await ApprovalService(session).get(engagement_id, approval_id, user)
    return ApprovalRead.model_validate(approval)


@router.post(
    "/{approval_id}/decision",
    response_model=ApprovalDecisionResult,
    summary="Approve or reject a proposal",
)
async def decide(
    engagement_id: uuid.UUID,
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    user: CurrentUserDep,
    session: DbSession,
) -> ApprovalDecisionResult:
    """Approving executes the payload immediately.

    A 200 with ``executed=false`` and an ``execution_error`` means the decision
    was recorded but the downstream write failed — the approval is not silently
    discarded, and it is visible as ``execution_failed`` for a retry.
    """
    approval, error = await ApprovalService(session).decide(
        engagement_id, approval_id, payload, user
    )
    return ApprovalDecisionResult(
        approval=ApprovalRead.model_validate(approval),
        executed=approval.status is ApprovalStatus.EXECUTED,
        execution_error=error,
    )


@router.post(
    "/bulk-decision",
    response_model=BulkApprovalResult,
    summary="Decide several proposals at once",
)
async def decide_bulk(
    engagement_id: uuid.UUID,
    payload: BulkApprovalDecision,
    user: CurrentUserDep,
    session: DbSession,
) -> BulkApprovalResult:
    """One meeting can produce a dozen proposals; deciding them one at a time
    is the difference between the PO using this and not."""
    return await ApprovalService(session).decide_bulk(engagement_id, payload, user)
