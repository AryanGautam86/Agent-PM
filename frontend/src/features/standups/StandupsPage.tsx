import { useState } from 'react'

import { Badge, StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Markdown } from '@/components/ui/Markdown'
import { Spinner } from '@/components/ui/Spinner'
import { EmptyState, ErrorState } from '@/components/ui/States'
import {
  useDeleteStandup,
  useGenerateStandup,
  useStandups,
} from '@/features/standups/api'
import { WriteStandup } from '@/features/standups/WriteStandup'
import { usePermissions } from '@/features/auth/usePermissions'
import { useSelectedEngagement } from '@/hooks/useEngagements'
import { formatDate, relativeTime } from '@/lib/format'
import type { StandupKind } from '@/types/api'

const FILTERS: Array<{ label: string; value: StandupKind | undefined }> = [
  { label: 'All', value: undefined },
  { label: 'Morning', value: 'morning' },
  { label: 'End of day', value: 'eod' },
]

export function StandupsPage() {
  const { engagementId } = useSelectedEngagement()
  const [kind, setKind] = useState<StandupKind | undefined>()

  const standups = useStandups(engagementId, kind)
  const generate = useGenerateStandup(engagementId)
  const remove = useDeleteStandup(engagementId)
  const { canModify } = usePermissions()

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Standups</h1>
          <p className="muted">
            Posted automatically at the engagement&rsquo;s configured times.
          </p>
        </div>
        {canModify && (
        <div className="page-actions">
          <Button
            variant="primary"
            loading={generate.isPending}
            onClick={() =>
              generate.mutate({ kind: 'morning', forceRegenerate: true })
            }
          >
            Regenerate morning
          </Button>
          <Button
            loading={generate.isPending}
            onClick={() => generate.mutate({ kind: 'eod', forceRegenerate: true })}
          >
            Regenerate EOD
          </Button>
        </div>
        )}
      </header>

      <WriteStandup engagementId={engagementId} />

      <div className="filter-row">
        {FILTERS.map((option) => (
          <button
            key={option.label}
            className={`chip ${kind === option.value ? 'chip-active' : ''}`}
            onClick={() => setKind(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {generate.isError && <ErrorState error={generate.error} />}

      {standups.isLoading ? (
        <Spinner label="Loading standups" />
      ) : standups.error ? (
        <ErrorState error={standups.error} onRetry={() => void standups.refetch()} />
      ) : (standups.data?.length ?? 0) === 0 ? (
        <EmptyState title="No standups yet" hint="Generate one to see it here." />
      ) : (
        <div className="stack">
          {standups.data?.map((standup) => (
            <Card
              key={standup.id}
              title={
                standup.topic
                  ? `${standup.topic} — ${formatDate(standup.for_date)}`
                  : `${standup.kind === 'morning' ? 'Morning plan' : 'End of day'} — ${formatDate(standup.for_date)}`
              }
              subtitle={
                standup.posted_at
                  ? `Posted ${relativeTime(standup.posted_at)}`
                  : `Generated ${relativeTime(standup.generated_at)}`
              }
              actions={
                <div className="badge-row">
                  {standup.author_user_id ? (
                    <Badge tone="info">written by you</Badge>
                  ) : (
                    <Badge tone="muted">agent</Badge>
                  )}
                  <StatusBadge value={standup.status} />
                  {canModify && (
                  <button
                    type="button"
                    className="icon-btn"
                    title="Delete this standup"
                    aria-label={`Delete standup for ${standup.for_date}`}
                    disabled={remove.isPending}
                    onClick={() => {
                      if (window.confirm('Delete this standup?')) {
                        remove.mutate(standup.id)
                      }
                    }}
                  >
                    ✕
                  </button>
                  )}
                </div>
              }
              accent={standup.blockers.length > 0 ? 'warning' : 'default'}
            >
              {standup.error ? (
                <p className="alert alert-error">{standup.error}</p>
              ) : (
                <Markdown source={standup.summary_markdown} />
              )}
              <footer className="card-footnote muted">
                {standup.blockers.length} blocker
                {standup.blockers.length === 1 ? '' : 's'} ·{' '}
                {standup.citations.length} citation
                {standup.citations.length === 1 ? '' : 's'}
                {standup.model && ` · ${standup.model}`}
              </footer>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
