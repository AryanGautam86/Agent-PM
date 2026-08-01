import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-keys'
import type { ActionItem, ActionItemStatus } from '@/types/api'

export function useActionItems(
  engagementId: string | null,
  status?: ActionItemStatus,
) {
  return useQuery({
    queryKey: queryKeys.actionItems(engagementId ?? 'none', status),
    queryFn: () =>
      api.get<ActionItem[]>(`/engagements/${engagementId}/action-items`, {
        status,
        limit: 200,
      }),
    enabled: Boolean(engagementId),
  })
}

export function useUpdateActionItem(engagementId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({
      itemId,
      patch,
    }: {
      itemId: string
      patch: Partial<
        Pick<ActionItem, 'status' | 'title' | 'owner_label' | 'due_at' | 'nudges_muted'>
      >
    }) =>
      api.patch<ActionItem>(
        `/engagements/${engagementId}/action-items/${itemId}`,
        patch,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.actionItems(engagementId ?? 'none'),
      })
    },
  })
}

export function useDeleteActionItem(engagementId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (itemId: string) =>
      api.delete<{ ok: boolean }>(
        `/engagements/${engagementId}/action-items/${itemId}`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.actionItems(engagementId ?? 'none'),
      })
    },
  })
}

export function useCreateActionItem(engagementId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: { title: string; owner_label?: string; due_at?: string }) =>
      api.post<ActionItem>(`/engagements/${engagementId}/action-items`, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.actionItems(engagementId ?? 'none'),
      })
    },
  })
}
