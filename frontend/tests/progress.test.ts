import { describe, expect, it } from 'vitest'

import { summarise } from '@/features/action_items/progress'
import type { ActionItem, ActionItemStatus } from '@/types/api'

function item(status: ActionItemStatus, overdue = false): ActionItem {
  return {
    id: crypto.randomUUID(),
    engagement_id: 'e',
    title: 't',
    description: null,
    owner_user_id: null,
    owner_label: null,
    due_at: null,
    status,
    source: 'manual',
    source_ref: null,
    citations: [],
    nudge_count: 0,
    last_nudged_at: null,
    escalated_at: null,
    nudges_muted: false,
    completed_at: null,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    is_overdue: overdue,
  }
}

describe('action item progress', () => {
  it('is zero with nothing to do', () => {
    expect(summarise([]).percent).toBe(0)
  })

  it('counts completion across the pod', () => {
    const p = summarise([item('done'), item('done'), item('open'), item('in_progress')])

    expect(p.percent).toBe(50)
    expect(p.done).toBe(2)
    expect(p.open).toBe(1)
    expect(p.inProgress).toBe(1)
  })

  it('excludes cancelled work from the denominator', () => {
    // 1 of 2 real items done. Cancelling the third must not drop this to 33%,
    // which would make the pod look worse for tidying up.
    const p = summarise([item('done'), item('open'), item('cancelled')])

    expect(p.percent).toBe(50)
    expect(p.cancelled).toBe(1)
  })

  it('reaches 100% when everything outstanding is done', () => {
    expect(summarise([item('done'), item('done'), item('cancelled')]).percent).toBe(100)
  })

  it('counts overdue separately from status', () => {
    // Overdue items are still open; they must appear in both counts, or late
    // work disappears from view.
    const p = summarise([item('open', true), item('open'), item('done')])

    expect(p.overdue).toBe(1)
    expect(p.open).toBe(2)
  })

  it('never reports progress on cancelled-only lists', () => {
    expect(summarise([item('cancelled'), item('cancelled')]).percent).toBe(0)
  })
})
