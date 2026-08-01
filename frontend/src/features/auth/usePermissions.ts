import { useAuth } from '@/features/auth/useAuth'

/**
 * What the signed-in user may do.
 *
 * Mirrors the backend rule so the UI can hide controls that would be refused,
 * rather than offering buttons that fail. The server is still the authority —
 * this only avoids showing a dead end.
 */
export function usePermissions() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  return {
    isAdmin,
    /** Everything except posting a standup. */
    canModify: isAdmin,
    /** Any member can write their own standup. */
    canWriteStandup: Boolean(user),
  }
}
