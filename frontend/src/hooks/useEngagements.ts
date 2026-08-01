import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'

import { api } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-keys'
import { useEngagementStore } from '@/store/engagement-store'
import type { Engagement, EngagementDetail } from '@/types/api'

export function useEngagements() {
  return useQuery({
    queryKey: queryKeys.engagements,
    queryFn: () => api.get<Engagement[]>('/engagements'),
  })
}

export function useEngagementDetail(engagementId: string | null) {
  return useQuery({
    queryKey: queryKeys.engagementDetail(engagementId ?? 'none'),
    queryFn: () => api.get<EngagementDetail>(`/engagements/${engagementId}`),
    enabled: Boolean(engagementId),
  })
}

/**
 * The engagement every page operates on.
 *
 * Falls back to the first one the user belongs to, and self-heals when the
 * persisted id points at an engagement they have lost access to.
 */
export function useSelectedEngagement() {
  const { data: engagements, isLoading, error } = useEngagements()
  const selectedId = useEngagementStore((state) => state.selectedId)
  const select = useEngagementStore((state) => state.select)

  const selected =
    engagements?.find((engagement) => engagement.id === selectedId) ??
    engagements?.[0] ??
    null

  useEffect(() => {
    if (selected && selected.id !== selectedId) {
      select(selected.id)
    }
  }, [selected, selectedId, select])

  return {
    engagements: engagements ?? [],
    engagement: selected,
    engagementId: selected?.id ?? null,
    isLoading,
    error,
    select,
  }
}
