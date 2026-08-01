import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-keys'
import type { Report, ReportKind, ReportStatus } from '@/types/api'

export function useReports(engagementId: string | null, kind?: ReportKind) {
  return useQuery({
    queryKey: queryKeys.reports(engagementId ?? 'none', kind),
    queryFn: () =>
      api.get<Report[]>(`/engagements/${engagementId}/reports`, { kind, limit: 25 }),
    enabled: Boolean(engagementId),
  })
}

export function useGenerateReport(engagementId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (kind: ReportKind) =>
      api.post<Report>(
        `/engagements/${engagementId}/reports/${
          kind === 'weekly_status' ? 'weekly-status' : 'planning-pack'
        }`,
        { force_regenerate: false },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.reports(engagementId ?? 'none'),
      })
    },
  })
}

/** Edit a draft, or move it along: draft -> approved -> sent. */
export function useUpdateReport(engagementId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      reportId,
      patch,
    }: {
      reportId: string
      patch: { title?: string; content_markdown?: string; status?: ReportStatus }
    }) => api.patch<Report>(`/engagements/${engagementId}/reports/${reportId}`, patch),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.reports(engagementId ?? 'none'),
      })
    },
  })
}

export function useMarkReportSent(engagementId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (reportId: string) =>
      api.post<Report>(`/engagements/${engagementId}/reports/${reportId}/sent`),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.reports(engagementId ?? 'none'),
      })
    },
  })
}
