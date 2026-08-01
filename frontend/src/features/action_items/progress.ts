import type { ActionItem } from '@/types/api'

export interface ActionProgress {
  total: number
  done: number
  inProgress: number
  open: number
  cancelled: number
  overdue: number
  /** Percent complete, excluding cancelled work. */
  percent: number
}

/**
 * Roll action items up into a completion figure.
 *
 * Two deliberate choices:
 *
 * - **Cancelled work is excluded from the denominator.** Cancelling something
 *   should not make a pod look further behind than before it was cancelled.
 * - **Overdue is counted separately, not as a status.** An item is both "open"
 *   and "overdue"; folding them together would hide work that is outstanding
 *   *and* late, which is precisely what needs attention.
 */
export function summarise(items: ActionItem[]): ActionProgress {
  const done = items.filter((i) => i.status === 'done').length
  const cancelled = items.filter((i) => i.status === 'cancelled').length
  const counted = items.length - cancelled

  return {
    total: items.length,
    done,
    inProgress: items.filter((i) => i.status === 'in_progress').length,
    open: items.filter((i) => i.status === 'open').length,
    cancelled,
    overdue: items.filter((i) => i.is_overdue).length,
    percent: counted === 0 ? 0 : Math.round((done / counted) * 100),
  }
}
