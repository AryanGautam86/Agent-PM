/**
 * Types mirroring the backend's Pydantic schemas.
 *
 * Hand-maintained rather than generated, so that the surface the UI depends on
 * is explicit and a backend field rename shows up as a TypeScript error rather
 * than as `undefined` at runtime. The backend serves an OpenAPI document at
 * `/openapi.json` if you would rather generate these later.
 */

export type AppRole = 'admin' | 'delivery_lead' | 'product_owner' | 'engineer'

export type PodRole =
  | 'product_owner'
  | 'delivery_lead'
  | 'tech_lead'
  | 'engineer'
  | 'qa'
  | 'designer'

export type AutonomyLevel = 'L1' | 'L2' | 'L3' | 'L4'
export type StandupKind = 'morning' | 'eod'
export type StandupStatus = 'draft' | 'posted' | 'failed'
export type RaidType = 'risk' | 'assumption' | 'issue' | 'dependency'
export type RaidStatus = 'open' | 'mitigating' | 'closed'
export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type ActionItemStatus = 'open' | 'in_progress' | 'done' | 'cancelled'
export type ApprovalStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'expired'
  | 'executed'
  | 'execution_failed'
export type ApprovalKind =
  | 'raid_gap_add'
  | 'raid_update'
  | 'jira_update'
  | 'risk_promotion'
  | 'weekly_status'
  | 'sprint_plan'
export type ReportKind = 'weekly_status' | 'sprint_planning_pack'
export type ReportStatus = 'draft' | 'approved' | 'sent'
export type RunStatus = 'running' | 'success' | 'failed' | 'skipped'

export interface ApiError {
  code: string
  message: string
  details: Record<string, unknown>
}

export interface CurrentUser {
  id: string
  email: string
  full_name: string | null
  avatar_url: string | null
  role: AppRole
  auth_provider: string | null
  is_active: boolean
}

export interface UserRead extends CurrentUser {
  last_seen_at: string | null
}

export interface Member {
  id: string
  user_id: string
  pod_role: PodRole
  jira_account_id: string | null
  github_login: string | null
  capacity_hours_per_sprint: number | null
  nudges_enabled: boolean
  user: UserRead
}

export interface Engagement {
  id: string
  slug: string
  name: string
  client_name: string | null
  description: string | null
  teams_channel_id: string | null
  teams_webhook_url: string | null
  jira_project_key: string | null
  jira_board_id: string | null
  github_repo: string | null
  raid_workbook_url: string | null
  timezone: string
  morning_post_time: string
  eod_post_time: string
  weekly_status_weekday: number
  autonomy_ceiling: AutonomyLevel
  task_overrides: Record<string, unknown>
  is_active: boolean
  agent_identity: string
}

export interface EngagementDetail extends Engagement {
  members: Member[]
}

export interface Citation {
  kind: string
  ref: string
  url?: string | null
}

export interface PersonBreakdown {
  person: string
  committed: number
  delivered: number
  pending: number
  blocked: number
  points_committed: number
  points_delivered: number
  issue_keys: string[]
}

export interface Blocker {
  issue_key: string
  summary: string
  assignee: string
  status: string
  age_days: number
  url: string | null
}

export interface EngagementSummary {
  id: string
  name: string
  slug: string
  client_name: string | null
  agent_identity: string
  open_tasks: number
  overdue_tasks: number
  done_tasks: number
  open_raid: number
  pending_approvals: number
  members: number
  last_standup_on: string | null
}

export interface Standup {
  id: string
  engagement_id: string
  kind: StandupKind
  for_date: string
  status: StandupStatus
  topic: string | null
  author_user_id: string | null
  summary_markdown: string
  per_person: PersonBreakdown[]
  blockers: Blocker[]
  highlights: Array<Record<string, unknown>>
  citations: Citation[]
  metrics: Record<string, string | number | null>
  model: string | null
  grounding_ratio: number | null
  generated_at: string | null
  posted_at: string | null
  error: string | null
}

export interface RaidItem {
  id: string
  engagement_id: string
  type: RaidType
  title: string
  description: string | null
  mitigation: string | null
  status: RaidStatus
  severity: Severity
  probability: Severity | null
  impact: Severity | null
  owner_user_id: string | null
  owner_label: string | null
  due_date: string | null
  source: string
  source_ref: string | null
  citations: Citation[]
  external_row_ref: string | null
  synced_at: string | null
  closed_at: string | null
  created_at: string
  updated_at: string
}

export interface RaidGapScanResult {
  checked_blockers: number
  gaps_found: number
  approvals_created: number
  gap_keys: string[]
  summary_markdown: string
}

export interface ActionItem {
  id: string
  engagement_id: string
  title: string
  description: string | null
  owner_user_id: string | null
  owner_label: string | null
  due_at: string | null
  status: ActionItemStatus
  source: string
  source_ref: string | null
  citations: Citation[]
  nudge_count: number
  last_nudged_at: string | null
  escalated_at: string | null
  nudges_muted: boolean
  completed_at: string | null
  created_at: string
  updated_at: string
  is_overdue: boolean
}

export interface Approval {
  id: string
  engagement_id: string
  kind: ApprovalKind
  status: ApprovalStatus
  title: string
  rationale: string | null
  payload: Record<string, unknown>
  citations: Citation[]
  requested_by_task: string
  agent_run_id: string | null
  expires_at: string | null
  decided_by_user_id: string | null
  decided_at: string | null
  decision_note: string | null
  edited_payload: Record<string, unknown> | null
  executed_at: string | null
  execution_result: Record<string, unknown> | null
  execution_error: string | null
  created_at: string
}

export interface ApprovalDecisionResult {
  approval: Approval
  executed: boolean
  execution_error: string | null
}

export interface Report {
  id: string
  engagement_id: string
  kind: ReportKind
  status: ReportStatus
  period_start: string
  period_end: string
  title: string
  content_markdown: string
  sections: Record<string, unknown>
  citations: Citation[]
  storage_url: string | null
  model: string | null
  approved_at: string | null
  sent_at: string | null
  created_at: string
}

export interface AgentRun {
  id: string
  engagement_id: string | null
  task_name: string
  trigger: string
  status: RunStatus
  autonomy_level: AutonomyLevel
  model_tier: string | null
  model: string | null
  input_digest: Record<string, unknown>
  output_summary: Record<string, unknown>
  grounding_ratio: number | null
  input_tokens: number | null
  output_tokens: number | null
  duration_ms: number | null
  started_at: string
  finished_at: string | null
  error_code: string | null
  error: string | null
}

export interface TaskCatalogEntry {
  name: string
  title: string
  description: string
  autonomy: AutonomyLevel
  model_tier: string
  requires_citations: boolean
  posts_to_channel: boolean
  needs_approval: boolean
  approval_kind: string
}

export interface HealthStatus {
  status: string
  environment: string
  version: string
  database: string | null
  integrations: Record<string, string>
  scheduler: string | null
}
