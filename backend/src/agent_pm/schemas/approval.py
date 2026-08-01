from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agent_pm.core.enums import ApprovalKind, ApprovalStatus
from agent_pm.schemas.common import ORMModel


class ApprovalRead(ORMModel):
    id: uuid.UUID
    engagement_id: uuid.UUID
    kind: ApprovalKind
    status: ApprovalStatus
    title: str
    rationale: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    requested_by_task: str
    agent_run_id: uuid.UUID | None = None
    expires_at: datetime | None = None
    decided_by_user_id: uuid.UUID | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None
    edited_payload: dict[str, Any] | None = None
    executed_at: datetime | None = None
    execution_result: dict[str, Any] | None = None
    execution_error: str | None = None
    created_at: datetime


class ApprovalDecision(BaseModel):
    """A PO's decision on a proposed change.

    ``edited_payload`` is how an approver corrects a proposal instead of
    rejecting it. When present it replaces the payload at execution time, and
    the edit is recorded — that difference is the "approved with minor/no
    edits" KPI.
    """

    approve: bool
    note: str | None = Field(default=None, max_length=2000)
    edited_payload: dict[str, Any] | None = None


class ApprovalDecisionResult(BaseModel):
    approval: ApprovalRead
    executed: bool
    execution_error: str | None = None


class BulkApprovalDecision(BaseModel):
    """Decide several proposals at once — one meeting produces many."""

    approval_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    approve: bool
    note: str | None = None


class BulkApprovalResult(BaseModel):
    decided: int
    executed: int
    failed: int
    errors: list[str] = Field(default_factory=list)
