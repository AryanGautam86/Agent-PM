import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-keys'
import type { AppRole, Member, PodRole, UserRead } from '@/types/api'

export function useMembers(engagementId: string | null) {
  return useQuery({
    queryKey: [...queryKeys.engagement(engagementId ?? 'none'), 'members'],
    queryFn: () => api.get<Member[]>(`/engagements/${engagementId}/members`),
    enabled: Boolean(engagementId),
  })
}

export function useAddMember(engagementId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (payload: {
      email: string
      pod_role: PodRole
      jira_account_id?: string
      github_login?: string
      capacity_hours_per_sprint?: number
    }) => api.post<Member>(`/engagements/${engagementId}/members`, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.engagement(engagementId ?? 'none'),
      })
    },
  })
}

export function useRemoveMember(engagementId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (userId: string) =>
      api.delete<{ ok: boolean }>(`/engagements/${engagementId}/members/${userId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.engagement(engagementId ?? 'none'),
      })
    },
  })
}

/** Admin-only: the application-wide role, which decides who can approve. */
export function useSetAppRole(engagementId: string | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: AppRole }) =>
      api.patch<UserRead>(`/auth/users/${userId}`, { role }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.engagement(engagementId ?? 'none'),
      })
    },
  })
}
