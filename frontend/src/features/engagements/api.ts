import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-keys'
import { useEngagementStore } from '@/store/engagement-store'
import type { Engagement } from '@/types/api'

export interface CreateEngagementInput {
  slug: string
  name: string
  client_name?: string
  timezone?: string
  jira_project_key?: string
  github_repo?: string
}

export function useCreateEngagement() {
  const queryClient = useQueryClient()
  const select = useEngagementStore((state) => state.select)

  return useMutation({
    mutationFn: (payload: CreateEngagementInput) =>
      api.post<Engagement>('/engagements', payload),
    onSuccess: (engagement) => {
      // Select it immediately — the creator is added as delivery lead by the
      // backend, so landing them anywhere else would be a dead end.
      select(engagement.id)
      void queryClient.invalidateQueries({ queryKey: queryKeys.engagements })
    },
  })
}

/**
 * Archive a project.
 *
 * The API keeps the row and its history — standups, RAID items, approvals and
 * agent runs all hang off an engagement, and a true delete would cascade
 * through the audit trail. Archiving removes it from every listing.
 */
export function useArchiveEngagement() {
  const queryClient = useQueryClient()
  const select = useEngagementStore((state) => state.select)

  return useMutation({
    mutationFn: (engagementId: string) =>
      api.delete<{ ok: boolean }>(`/engagements/${engagementId}`),
    onSuccess: (_result, engagementId) => {
      // Clear the selection if it pointed at the archived project, otherwise
      // the sidebar keeps showing something that no longer exists.
      if (useEngagementStore.getState().selectedId === engagementId) {
        select(null)
      }
      void queryClient.invalidateQueries({ queryKey: queryKeys.engagements })
    },
  })
}

/** Slugify a display name: lowercase, hyphens, no leading/trailing dashes. */
export function toSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)
}
