/**
 * Completion overview for a pod's action items.
 *
 * The arithmetic lives in ./progress.ts so it can be tested without rendering.
 */

import { summarise } from '@/features/action_items/progress'
import type { ActionItem } from '@/types/api'

export function ProgressSummary({ items }: { items: ActionItem[] }) {
  const p = summarise(items)

  if (p.total === 0) return null

  const tone = p.overdue > 0 ? 'danger' : p.percent === 100 ? 'success' : 'accent'

  return (
    <section className="progress-card">
      <div className="progress-head">
        <div>
          <span className="progress-percent">{p.percent}%</span>
          <span className="muted">
            {' '}
            complete · {p.done} of {p.total - p.cancelled} done
          </span>
        </div>
        {p.overdue > 0 && (
          <span className="badge badge-danger">{p.overdue} overdue</span>
        )}
      </div>

      <div
        className={`progress-track progress-${tone}`}
        role="progressbar"
        aria-valuenow={p.percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Action item completion"
      >
        <div className="progress-fill" style={{ width: `${p.percent}%` }} />
      </div>

      <div className="progress-legend">
        <Stat label="Open" value={p.open} />
        <Stat label="In progress" value={p.inProgress} />
        <Stat label="Done" value={p.done} />
        {p.cancelled > 0 && <Stat label="Cancelled" value={p.cancelled} />}
      </div>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <span className="progress-stat">
      <strong>{value}</strong> <span className="muted">{label}</span>
    </span>
  )
}
