import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-keys'
import type { Standup, StandupKind } from '@/types/api'

export function useStandups(engagementId: string | null, kind?: StandupKind) {
  return useQuery({
    queryKey: queryKeys.standups(engagementId ?? 'none', kind),
    queryFn: () =>
      api.get<Standup[]>(`/engagements/${engagementId}/standups`, {
        kind,
        limit: 30,
      }),
    enabled: Boolean(engagementId),
  })
}

export interface WriteStandupInput {
  kind: StandupKind
  topic: string
  summary_markdown: string
  for_date?: string
}

/** Post a standup a person wrote, rather than asking the agent for one. */
export function useWriteStandup(engagementId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: WriteStandupInput) =>
      api.post<Standup>(`/engagements/${engagementId}/standups`, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.engagement(engagementId ?? 'none'),
      })
    },
  })
}

export function useDeleteStandup(engagementId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (standupId: string) =>
      api.delete<{ ok: boolean }>(
        `/engagements/${engagementId}/standups/${standupId}`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.engagement(engagementId ?? 'none'),
      })
    },
  })
}

export function useGenerateStandup(engagementId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      kind,
      forceRegenerate = false,
    }: {
      kind: StandupKind
      forceRegenerate?: boolean
    }) =>
      api.post<Standup>(
        `/engagements/${engagementId}/standups/${kind === 'morning' ? 'morning' : 'eod'}`,
        { force_regenerate: forceRegenerate },
      ),
    onSuccess: () => {
      // Generation also creates an agent run, and can create approvals via
      // downstream tasks, so refresh the whole engagement subtree.
      void queryClient.invalidateQueries({
        queryKey: queryKeys.engagement(engagementId ?? 'none'),
      })
    },
  })
}
