/**
 * Client status reports and sprint planning packs.
 *
 * Review happens here rather than in a separate approvals queue: a report is a
 * draft until someone approves it, and only an approved report can be marked
 * sent. Two steps on purpose — this is the one output a client reads directly,
 * so it should not be one careless click away from going out.
 */

import { StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Markdown } from '@/components/ui/Markdown'
import { Spinner } from '@/components/ui/Spinner'
import { EmptyState, ErrorState } from '@/components/ui/States'
import {
  useGenerateReport,
  useMarkReportSent,
  useReports,
  useUpdateReport,
} from '@/features/reports/api'
import { usePermissions } from '@/features/auth/usePermissions'
import { useSelectedEngagement } from '@/hooks/useEngagements'
import { formatDate } from '@/lib/format'

export function ReportsPage() {
  const { engagementId } = useSelectedEngagement()

  const reports = useReports(engagementId)
  const generate = useGenerateReport(engagementId)
  const update = useUpdateReport(engagementId)
  const markSent = useMarkReportSent(engagementId)
  const { canModify } = usePermissions()

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Reports</h1>
          <p className="muted">
            Client status and planning packs. Each is a draft until you approve
            it.
          </p>
        </div>
        {canModify && (
        <div className="page-actions">
          <Button
            variant="primary"
            loading={generate.isPending}
            onClick={() => generate.mutate('weekly_status')}
          >
            Draft weekly status
          </Button>
          <Button
            loading={generate.isPending}
            onClick={() => generate.mutate('sprint_planning_pack')}
          >
            Draft planning pack
          </Button>
        </div>
        )}
      </header>

      {generate.isError && <ErrorState error={generate.error} />}
      {update.isError && <ErrorState error={update.error} />}
      {markSent.isError && <ErrorState error={markSent.error} />}

      {reports.isLoading ? (
        <Spinner label="Loading reports" />
      ) : reports.error ? (
        <ErrorState error={reports.error} onRetry={() => void reports.refetch()} />
      ) : (reports.data?.length ?? 0) === 0 ? (
        <EmptyState
          title="No reports yet"
          hint="Weekly drafts are also generated automatically on the configured weekday."
        />
      ) : (
        <div className="stack">
          {reports.data?.map((report) => (
            <Card
              key={report.id}
              title={report.title}
              subtitle={`${formatDate(report.period_start)} – ${formatDate(report.period_end)}`}
              actions={
                <div className="badge-row">
                  {typeof report.sections.status_rag === 'string' && (
                    <StatusBadge value={String(report.sections.status_rag)} />
                  )}
                  <StatusBadge value={report.status} />
                </div>
              }
            >
              <Markdown source={report.content_markdown} />

              {canModify && (
              <div className="inline-actions">
                {report.status === 'draft' && (
                  <Button
                    size="sm"
                    variant="primary"
                    disabled={update.isPending}
                    onClick={() =>
                      update.mutate({
                        reportId: report.id,
                        patch: { status: 'approved' },
                      })
                    }
                  >
                    Approve
                  </Button>
                )}
                {report.status === 'approved' && (
                  <>
                    <Button
                      size="sm"
                      variant="primary"
                      disabled={markSent.isPending}
                      onClick={() => markSent.mutate(report.id)}
                    >
                      Mark as sent
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={update.isPending}
                      onClick={() =>
                        update.mutate({
                          reportId: report.id,
                          patch: { status: 'draft' },
                        })
                      }
                    >
                      Back to draft
                    </Button>
                  </>
                )}
              </div>
              )}

              <footer className="card-footnote muted">
                {report.citations.length} citation
                {report.citations.length === 1 ? '' : 's'}
                {report.model && ` · ${report.model}`}
                {report.sent_at && ` · sent ${formatDate(report.sent_at)}`}
              </footer>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
