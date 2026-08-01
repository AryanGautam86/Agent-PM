/**
 * Every project at a glance, with the numbers that decide where attention goes.
 *
 * Counts come from a single backend endpoint rather than one request per
 * project, so this stays cheap as projects multiply.
 */

import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Spinner'
import { ErrorState } from '@/components/ui/States'
import { api } from '@/lib/api-client'
import { formatDate } from '@/lib/format'
import { useEngagementStore } from '@/store/engagement-store'
import type { EngagementSummary } from '@/types/api'

function useProjectSummaries() {
  return useQuery({
    queryKey: ['engagement-summaries'],
    queryFn: () => api.get<EngagementSummary[]>('/engagements/summary'),
  })
}

function percent(s: EngagementSummary): number {
  const total = s.open_tasks + s.done_tasks
  return total === 0 ? 0 : Math.round((s.done_tasks / total) * 100)
}

export function ProjectOverview() {
  const summaries = useProjectSummaries()
  const select = useEngagementStore((state) => state.select)

  if (summaries.isLoading) return <Spinner label="Loading projects" />
  if (summaries.error) {
    return (
      <ErrorState error={summaries.error} onRetry={() => void summaries.refetch()} />
    )
  }

  const projects = summaries.data ?? []
  if (projects.length === 0) return null

  return (
    <Card
      title={`Projects (${projects.length})`}
      subtitle="Everything you belong to. Click one to make it the active project."
      actions={
        <Link className="link" to="/action-items">
          Manage
        </Link>
      }
    >
      <div className="project-grid">
        {projects.map((s) => {
          const pct = percent(s)
          const tone =
            s.overdue_tasks > 0 ? 'danger' : pct === 100 ? 'success' : 'accent'
          return (
            <button
              key={s.id}
              type="button"
              className="project-tile"
              onClick={() => select(s.id)}
            >
              <div className="project-tile-head">
                <strong>{s.name}</strong>
                {s.pending_approvals > 0 && (
                  <Badge tone="warning">{s.pending_approvals} to approve</Badge>
                )}
              </div>
              <p className="muted project-tile-sub">
                {s.client_name ?? 'Internal'} · {s.members} member
                {s.members === 1 ? '' : 's'}
              </p>

              <div className={`progress-track progress-${tone}`}>
                <div className="progress-fill" style={{ width: `${pct}%` }} />
              </div>

              <div className="project-tile-counts">
                <Count label="tasks done" value={`${s.done_tasks}/${s.done_tasks + s.open_tasks}`} />
                <Count label="RAID open" value={s.open_raid} />
                {s.overdue_tasks > 0 ? (
                  <Count label="overdue" value={s.overdue_tasks} tone="danger" />
                ) : (
                  <Count label="overdue" value={0} />
                )}
              </div>

              <p className="muted project-tile-foot">
                {s.last_standup_on
                  ? `Last standup ${formatDate(s.last_standup_on)}`
                  : 'No standup yet'}
              </p>
            </button>
          )
        })}
      </div>
    </Card>
  )
}

function Count({
  label,
  value,
  tone,
}: {
  label: string
  value: string | number
  tone?: 'danger'
}) {
  return (
    <span className="project-count">
      <strong className={tone === 'danger' ? 'text-danger' : undefined}>{value}</strong>
      <span className="muted"> {label}</span>
    </span>
  )
}
