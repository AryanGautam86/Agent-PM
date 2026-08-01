/**
 * Query key factory.
 *
 * Centralised so an invalidation cannot miss a cache entry through a typo —
 * `queryKeys.engagement(id)` is the prefix of everything scoped to that
 * engagement, so invalidating it clears the whole pod's data at once.
 */

export const queryKeys = {
  me: ['me'] as const,
  taskCatalog: ['task-catalog'] as const,
  engagements: ['engagements'] as const,

  engagement: (id: string) => ['engagements', id] as const,
  engagementDetail: (id: string) => ['engagements', id, 'detail'] as const,

  standups: (id: string, kind?: string) =>
    ['engagements', id, 'standups', kind ?? 'all'] as const,
  raid: (id: string, status?: string) =>
    ['engagements', id, 'raid', status ?? 'all'] as const,
  actionItems: (id: string, status?: string) =>
    ['engagements', id, 'action-items', status ?? 'all'] as const,
  approvals: (id: string, status?: string) =>
    ['engagements', id, 'approvals', status ?? 'all'] as const,
  reports: (id: string, kind?: string) =>
    ['engagements', id, 'reports', kind ?? 'all'] as const,
  runs: (id: string) => ['engagements', id, 'runs'] as const,
} as const
