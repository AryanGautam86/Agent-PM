/**
 * The pod's morning view: today's standup, what needs a decision, what is
 * blocked, and what is overdue — in that order, because that is the order a
 * delivery lead cares about.
 */

import { Link } from 'react-router-dom'

import { Badge, StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Markdown } from '@/components/ui/Markdown'
import { Spinner } from '@/components/ui/Spinner'
import { EmptyState, ErrorState } from '@/components/ui/States'
import { useActionItems } from '@/features/action_items/api'
import { ProjectOverview } from '@/features/dashboard/ProjectOverview'
import { useGenerateStandup, useStandups } from '@/features/standups/api'
import { useSelectedEngagement } from '@/hooks/useEngagements'
import { formatDate, relativeTime } from '@/lib/format'

export function DashboardPage() {
  const { engagement, engagementId } = useSelectedEngagement()

  const standups = useStandups(engagementId)
  const actions = useActionItems(engagementId, 'open')
  const generate = useGenerateStandup(engagementId)

  if (!engagement) {
    return (
      <EmptyState
        title="No engagement selected"
        hint="You are not a member of any pod yet. Ask an administrator to add you."
      />
    )
  }

  const latest = standups.data?.[0]
  const overdue = actions.data?.filter((item) => item.is_overdue) ?? []

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{engagement.name}</h1>
          <p className="muted">
            {engagement.client_name ?? 'Internal'} · {engagement.agent_identity} ·{' '}
            {engagement.timezone}
          </p>
        </div>
        <div className="page-actions">
          <Button
            variant="primary"
            loading={generate.isPending}
            onClick={() => generate.mutate({ kind: 'morning' })}
          >
            Generate morning plan
          </Button>
          <Button
            loading={generate.isPending}
            onClick={() => generate.mutate({ kind: 'eod' })}
          >
            Generate EOD
          </Button>
        </div>
      </header>

      {generate.isError && <ErrorState error={generate.error} />}

      <ProjectOverview />

      <div className="stat-row">
        <Stat
          label="Open tasks"
          value={actions.data?.length ?? 0}
          tone="neutral"
          to="/action-items"
        />
        <Stat
          label="Overdue"
          value={overdue.length}
          tone={overdue.length ? 'danger' : 'success'}
          to="/action-items"
        />
      </div>

      <Card
        title={latest ? `${titleFor(latest.kind)} — ${formatDate(latest.for_date)}` : 'Latest standup'}
        subtitle={
          latest
            ? `${latest.status} · generated ${relativeTime(latest.generated_at)}`
            : undefined
        }
        actions={latest ? <StatusBadge value={latest.status} /> : undefined}
      >
        {standups.isLoading ? (
          <Spinner label="Loading standups" />
        ) : standups.error ? (
          <ErrorState error={standups.error} onRetry={() => void standups.refetch()} />
        ) : !latest ? (
          <EmptyState
            title="No standups yet"
            hint="Generate one now, or wait for the scheduled 08:00 post."
          />
        ) : (
          <>
            <Markdown source={latest.summary_markdown} />

            {latest.per_person.length > 0 && (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Person</th>
                      <th>Committed</th>
                      <th>Delivered</th>
                      <th>Pending</th>
                      <th>Blocked</th>
                    </tr>
                  </thead>
                  <tbody>
                    {latest.per_person.map((person) => (
                      <tr key={person.person}>
                        <td>{person.person}</td>
                        <td>{person.committed}</td>
                        <td>{person.delivered}</td>
                        <td>{person.pending}</td>
                        <td>
                          {person.blocked > 0 ? (
                            <Badge tone="danger">{person.blocked}</Badge>
                          ) : (
                            '—'
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {latest.blockers.length > 0 && (
              <div className="subsection">
                <h3>Blockers</h3>
                <ul className="list">
                  {latest.blockers.map((blocker) => (
                    <li key={blocker.issue_key}>
                      <span className="mono">{blocker.issue_key}</span>{' '}
                      {blocker.summary}
                      <span className="muted">
                        {' '}
                        — {blocker.assignee}, blocked {blocker.age_days}d
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <footer className="card-footnote muted">
              {latest.citations.length} citation
              {latest.citations.length === 1 ? '' : 's'}
              {latest.grounding_ratio !== null &&
                ` · ${Math.round(latest.grounding_ratio * 100)}% of claims grounded`}
              {latest.model && ` · ${latest.model}`}
            </footer>
          </>
        )}
      </Card>

    </div>
  )
}

function titleFor(kind: string): string {
  return kind === 'morning' ? 'Morning sprint plan' : 'End-of-day summary'
}

function Stat({
  label,
  value,
  tone,
  to,
}: {
  label: string
  value: number
  tone: 'neutral' | 'info' | 'warning' | 'danger' | 'success'
  to: string
}) {
  return (
    <Link to={to} className={`stat stat-${tone}`}>
      <span className="stat-value">{value}</span>
      <span className="stat-label">{label}</span>
    </Link>
  )
}
