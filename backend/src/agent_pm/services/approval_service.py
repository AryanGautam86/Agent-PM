"""Human-in-the-loop approvals, and the execution of approved payloads.

This is the file that makes "zero unapproved writes" true rather than intended.
Nothing else in the codebase calls ``jira.apply_update`` or
``storage.append_raid_row``; those calls exist here, downstream of a recorded
decision by an authorised human, and they operate on
:attr:`Approval.effective_payload` — the exact object that was approved.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent_pm.core.clock import utc_now
from agent_pm.core.enums import (
    ApprovalKind,
    ApprovalStatus,
    RaidSource,
    RaidStatus,
    RaidType,
    ReportStatus,
    Severity,
)
from agent_pm.core.errors import AgentPMError, ConflictError, ValidationError
from agent_pm.core.logging import get_logger
from agent_pm.integrations.jira.models import JiraUpdate
from agent_pm.integrations.registry import IntegrationRegistry, get_registry
from agent_pm.integrations.storage.base import RaidRow
from agent_pm.models.approval import Approval
from agent_pm.models.raid import RaidItem
from agent_pm.repositories.approval import ApprovalRepository
from agent_pm.repositories.raid import RaidRepository
from agent_pm.repositories.report import ReportRepository
from agent_pm.schemas.approval import (
    ApprovalDecision,
    BulkApprovalDecision,
    BulkApprovalResult,
)
from agent_pm.schemas.auth import CurrentUser
from agent_pm.services.engagement_service import EngagementService

logger = get_logger(__name__)

RAID_KINDS = frozenset(
    {ApprovalKind.RAID_GAP_ADD, ApprovalKind.RAID_UPDATE, ApprovalKind.RISK_PROMOTION}
)
REPORT_KINDS = frozenset({ApprovalKind.WEEKLY_STATUS, ApprovalKind.SPRINT_PLAN})


class ApprovalService:
    def __init__(
        self, session: AsyncSession, *, registry: IntegrationRegistry | None = None
    ) -> None:
        self.session = session
        self.registry = registry or get_registry()
        self.approvals = ApprovalRepository(session)
        self.raid = RaidRepository(session)
        self.reports = ReportRepository(session)
        self.engagements = EngagementService(session)

    # ---- reads -----------------------------------------------------------

    async def list_items(
        self,
        engagement_id: uuid.UUID,
        user: CurrentUser,
        *,
        status: ApprovalStatus | None = None,
        kind: ApprovalKind | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Approval]:
        await self.engagements.require_access(engagement_id, user)
        return await self.approvals.list_all(
            engagement_id, status=status, kind=kind, limit=limit, offset=offset
        )

    async def get(
        self, engagement_id: uuid.UUID, approval_id: uuid.UUID, user: CurrentUser
    ) -> Approval:
        await self.engagements.require_access(engagement_id, user)
        return await self.approvals.get_for_engagement(engagement_id, approval_id)

    # ---- decisions -------------------------------------------------------

    async def decide(
        self,
        engagement_id: uuid.UUID,
        approval_id: uuid.UUID,
        decision: ApprovalDecision,
        user: CurrentUser,
    ) -> tuple[Approval, str | None]:
        engagement = await self.engagements.require_approver(engagement_id, user)
        approval = await self.approvals.get_for_engagement(engagement_id, approval_id)

        if not approval.is_pending:
            raise ConflictError(
                f"This approval was already {approval.status.value}",
                details={"status": approval.status.value},
            )
        if approval.is_expired:
            # Auto-deny on timeout, per the brief. Expiry is checked here as
            # well as by the sweep, so a stale card cannot be approved late.
            approval.status = ApprovalStatus.EXPIRED
            approval.decided_at = utc_now()
            await self.session.flush()
            raise ConflictError("This approval expired and was automatically denied")

        approval.decided_by_user_id = user.id
        approval.decided_at = utc_now()
        approval.decision_note = decision.note

        if decision.edited_payload is not None:
            if not isinstance(decision.edited_payload, dict):
                raise ValidationError("edited_payload must be an object")
            approval.edited_payload = decision.edited_payload

        if not decision.approve:
            approval.status = ApprovalStatus.REJECTED
            await self.session.flush()
            logger.info("approval_rejected", extra={"approval_id": str(approval.id)})
            return approval, None

        approval.status = ApprovalStatus.APPROVED
        await self.session.flush()

        error = await self._execute(approval, engagement_id, engagement.raid_workbook_url)
        return approval, error

    async def decide_bulk(
        self,
        engagement_id: uuid.UUID,
        decision: BulkApprovalDecision,
        user: CurrentUser,
    ) -> BulkApprovalResult:
        result = BulkApprovalResult(decided=0, executed=0, failed=0)
        for approval_id in decision.approval_ids:
            try:
                approval, error = await self.decide(
                    engagement_id,
                    approval_id,
                    ApprovalDecision(approve=decision.approve, note=decision.note),
                    user,
                )
                result.decided += 1
                if approval.status is ApprovalStatus.EXECUTED:
                    result.executed += 1
                if error:
                    result.failed += 1
                    result.errors.append(f"{approval_id}: {error}")
            except AgentPMError as exc:
                # One bad approval must not abort the rest of the batch.
                result.failed += 1
                result.errors.append(f"{approval_id}: {exc.message}")
        return result

    # ---- execution -------------------------------------------------------

    async def _execute(
        self, approval: Approval, engagement_id: uuid.UUID, workbook_url: str | None
    ) -> str | None:
        payload = approval.effective_payload
        try:
            if approval.kind in RAID_KINDS:
                outcome = await self._execute_raid(approval, engagement_id, workbook_url)
            elif approval.kind is ApprovalKind.JIRA_UPDATE:
                outcome = await self._execute_jira(payload)
            elif approval.kind in REPORT_KINDS:
                outcome = await self._execute_report(payload, approval)
            else:
                raise ValidationError(
                    f"No executor for approval kind {approval.kind.value}"
                )
        except AgentPMError as exc:
            approval.status = ApprovalStatus.EXECUTION_FAILED
            approval.execution_error = exc.message
            approval.executed_at = utc_now()
            await self.session.flush()
            logger.error(
                "approval_execution_failed",
                extra={"approval_id": str(approval.id), "error": exc.message},
            )
            return exc.message

        approval.status = ApprovalStatus.EXECUTED
        approval.execution_result = outcome
        approval.executed_at = utc_now()
        approval.execution_error = None
        await self.session.flush()
        logger.info(
            "approval_executed",
            extra={"approval_id": str(approval.id), "kind": approval.kind.value},
        )
        return None

    async def _execute_raid(
        self, approval: Approval, engagement_id: uuid.UUID, workbook_url: str | None
    ) -> dict[str, Any]:
        payload = approval.effective_payload
        source_ref = payload.get("source_ref")

        # Re-check for a duplicate at execution time: an approval may have sat
        # in the queue while somebody added the row by hand.
        if source_ref:
            existing = await self.raid.find_by_source_ref(engagement_id, str(source_ref))
            if existing is not None:
                return {"skipped": True, "reason": "already in RAID", "id": str(existing.id)}

        item = RaidItem(
            engagement_id=engagement_id,
            type=RaidType(payload.get("type", RaidType.RISK.value)),
            title=str(payload.get("title", "")).strip() or "(untitled)",
            description=payload.get("description"),
            mitigation=payload.get("mitigation"),
            status=RaidStatus.OPEN,
            severity=Severity(payload.get("severity", Severity.MEDIUM.value)),
            owner_label=payload.get("owner_label"),
            source=RaidSource(payload.get("source", RaidSource.MANUAL.value)),
            source_ref=str(source_ref) if source_ref else None,
            citations=approval.citations,
        )
        self.raid.add(item)
        await self.session.flush()

        result: dict[str, Any] = {"raid_item_id": str(item.id), "workbook_synced": False}

        if workbook_url:
            row = await self.registry.storage.append_raid_row(
                workbook_url,
                RaidRow(
                    type=item.type.value,
                    title=item.title,
                    description=item.description,
                    owner=item.owner_label,
                    status=item.status.value,
                    severity=item.severity.value,
                    mitigation=item.mitigation,
                    source_ref=item.source_ref,
                ),
            )
            item.external_row_ref = row.row_ref
            item.synced_at = utc_now()
            result["workbook_synced"] = True
            result["row_ref"] = row.row_ref
            await self.session.flush()

        return result

    async def _execute_jira(self, payload: dict[str, Any]) -> dict[str, Any]:
        update = JiraUpdate.model_validate(payload)
        return await self.registry.jira.apply_update(update)

    async def _execute_report(
        self, payload: dict[str, Any], approval: Approval
    ) -> dict[str, Any]:
        report_id = payload.get("report_id")
        if not report_id:
            raise ValidationError("Report approval payload has no report_id")

        report = await self.reports.get_for_engagement(
            approval.engagement_id, uuid.UUID(str(report_id))
        )
        report.status = ReportStatus.APPROVED
        report.approved_by_user_id = approval.decided_by_user_id
        report.approved_at = utc_now()
        await self.session.flush()
        return {"report_id": str(report.id), "status": report.status.value}

    # ---- maintenance -----------------------------------------------------

    async def expire_stale(self) -> int:
        """Auto-deny approvals past their expiry. Run by the scheduler."""
        stale = await self.approvals.list_expired()
        for approval in stale:
            approval.status = ApprovalStatus.EXPIRED
            approval.decided_at = utc_now()
            approval.decision_note = "Expired without a decision (auto-denied)."
        if stale:
            await self.session.flush()
            logger.info("approvals_expired", extra={"count": len(stale)})
        return len(stale)
