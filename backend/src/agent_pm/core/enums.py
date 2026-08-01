"""Shared vocabulary.

Every enum here is stored in Postgres as a plain string column, not a native
Postgres enum type. Adding a value is then a code change rather than a
migration that rewrites a type. See docs/ARCHITECTURE.md section 4.
"""

from __future__ import annotations

from enum import StrEnum


class Environment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class AppRole(StrEnum):
    """Application-wide role, distinct from a person's role within a pod."""

    ADMIN = "admin"
    DELIVERY_LEAD = "delivery_lead"
    PRODUCT_OWNER = "product_owner"
    ENGINEER = "engineer"

    @property
    def can_approve(self) -> bool:
        """Whether this role may decide human-in-the-loop approvals."""
        return self in {AppRole.ADMIN, AppRole.DELIVERY_LEAD, AppRole.PRODUCT_OWNER}


class PodRole(StrEnum):
    PRODUCT_OWNER = "product_owner"
    DELIVERY_LEAD = "delivery_lead"
    TECH_LEAD = "tech_lead"
    ENGINEER = "engineer"
    QA = "qa"
    DESIGNER = "designer"


class AutonomyLevel(StrEnum):
    """How much a task may do without a human.

    The runner, not the task, enforces this — see services/agent_runner.py.
    """

    L1_SUGGEST = "L1"
    L2_DRAFT_APPROVE = "L2"
    L3_ACT_REVIEW = "L3"
    L4_AUTONOMOUS = "L4"

    @property
    def may_write_externally(self) -> bool:
        """L1 and L2 must never reach an external system unapproved."""
        return self in {AutonomyLevel.L3_ACT_REVIEW, AutonomyLevel.L4_AUTONOMOUS}

    @property
    def requires_approval(self) -> bool:
        return self is AutonomyLevel.L2_DRAFT_APPROVE


class ModelTier(StrEnum):
    """Which model a task routes to.

    STRUCTURED: high-volume deterministic work (standups, gap scans).
    NARRATIVE:  client-facing prose where quality justifies the cost.
    """

    STRUCTURED = "structured"
    NARRATIVE = "narrative"


class StandupKind(StrEnum):
    MORNING = "morning"
    EOD = "eod"


class StandupStatus(StrEnum):
    DRAFT = "draft"
    POSTED = "posted"
    FAILED = "failed"


class RaidType(StrEnum):
    RISK = "risk"
    ASSUMPTION = "assumption"
    ISSUE = "issue"
    DEPENDENCY = "dependency"


class RaidStatus(StrEnum):
    OPEN = "open"
    MITIGATING = "mitigating"
    CLOSED = "closed"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RaidSource(StrEnum):
    MANUAL = "manual"
    JIRA_GAP_SCAN = "jira_gap_scan"
    MEETING_OUTCOME = "meeting_outcome"
    BLOCKER_PROMOTION = "blocker_promotion"


class ActionItemStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class ActionItemSource(StrEnum):
    MEETING_OUTCOME = "meeting_outcome"
    STANDUP = "standup"
    MANUAL = "manual"
    JIRA = "jira"


class ApprovalKind(StrEnum):
    """What an approval, once granted, will execute."""

    RAID_GAP_ADD = "raid_gap_add"
    RAID_UPDATE = "raid_update"
    JIRA_UPDATE = "jira_update"
    RISK_PROMOTION = "risk_promotion"
    WEEKLY_STATUS = "weekly_status"
    SPRINT_PLAN = "sprint_plan"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"
    EXECUTION_FAILED = "execution_failed"


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class EventType(StrEnum):
    """A2A contract. Inbound from the Meeting Agent, outbound to consumers."""

    MEETING_OUTCOME = "meeting_outcome"
    PM_SUMMARY = "pm_summary"
    PM_EOD_SUMMARY = "pm_eod_summary"


class EventStatus(StrEnum):
    RECEIVED = "received"
    PROCESSED = "processed"
    REJECTED = "rejected"
    FAILED = "failed"


class ReportKind(StrEnum):
    WEEKLY_STATUS = "weekly_status"
    SPRINT_PLANNING_PACK = "sprint_planning_pack"


class ReportStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"
