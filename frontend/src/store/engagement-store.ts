/**
 * The currently selected engagement.
 *
 * Persisted to localStorage so a refresh does not dump a PO back to the pod
 * picker. Only the id is stored; the engagement itself always comes from the
 * API, so a stale name can never be shown.
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface EngagementState {
  selectedId: string | null
  select: (id: string | null) => void
}

export const useEngagementStore = create<EngagementState>()(
  persist(
    (set) => ({
      selectedId: null,
      select: (id) => set({ selectedId: id }),
    }),
    { name: 'agent-pm.engagement' },
  ),
)
