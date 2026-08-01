export type BadgeTone =
  | 'neutral'
  | 'info'
  | 'success'
  | 'warning'
  | 'danger'
  | 'muted'

/**
 * Maps the API's several vocabularies — severity, statuses, autonomy levels —
 * onto one small set of tones, so the same concept never appears in two
 * colours on two screens.
 */
const TONE_BY_VALUE: Record<string, BadgeTone> = {
  // severity
  low: 'muted',
  medium: 'info',
  high: 'warning',
  critical: 'danger',
  // RAID and action item statuses
  open: 'warning',
  mitigating: 'info',
  closed: 'success',
  done: 'success',
  in_progress: 'info',
  cancelled: 'muted',
  // standup statuses
  draft: 'muted',
  posted: 'success',
  failed: 'danger',
  // approval statuses
  pending: 'warning',
  approved: 'success',
  executed: 'success',
  rejected: 'muted',
  expired: 'muted',
  execution_failed: 'danger',
  // report and run statuses
  sent: 'success',
  success: 'success',
  running: 'info',
  skipped: 'muted',
  // RAG
  green: 'success',
  amber: 'warning',
  red: 'danger',
  // autonomy levels — higher means more freedom, so more caution
  L1: 'muted',
  L2: 'info',
  L3: 'warning',
  L4: 'danger',
}

export function toneFor(value: string | null | undefined): BadgeTone {
  if (!value) return 'neutral'
  return TONE_BY_VALUE[value] ?? 'neutral'
}
