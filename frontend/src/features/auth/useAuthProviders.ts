/**
 * Asks the Supabase project which sign-in methods are actually enabled.
 *
 * `/auth/v1/settings` is public (it only needs the publishable key) and is the
 * same endpoint the Supabase dashboard uses. Reading it means the login page
 * shows what genuinely works instead of a Google button that errors, and a new
 * provider appears the moment it is enabled — no redeploy.
 */

import { useEffect, useState } from 'react'

import { isSupabaseConfigured, supabaseAnonKey, supabaseUrl } from '@/lib/supabase'

export interface AuthProviders {
  email: boolean
  google: boolean
  /** False when the project refuses new accounts, which changes the wording. */
  signupsOpen: boolean
  loading: boolean
}

const FALLBACK: AuthProviders = {
  // Assume email works so a failed probe never blocks the primary path.
  email: true,
  google: false,
  signupsOpen: true,
  loading: false,
}

export function useAuthProviders(): AuthProviders {
  const [state, setState] = useState<AuthProviders>({ ...FALLBACK, loading: true })

  useEffect(() => {
    if (!isSupabaseConfigured) {
      setState({ ...FALLBACK, email: false, loading: false })
      return
    }

    let active = true
    const controller = new AbortController()

    fetch(`${supabaseUrl}/auth/v1/settings`, {
      headers: { apikey: supabaseAnonKey },
      signal: controller.signal,
    })
      .then((response) => (response.ok ? response.json() : Promise.reject(response)))
      .then((data: { external?: Record<string, boolean>; disable_signup?: boolean }) => {
        if (!active) return
        setState({
          email: Boolean(data.external?.email),
          google: Boolean(data.external?.google),
          signupsOpen: !data.disable_signup,
          loading: false,
        })
      })
      .catch(() => {
        // A probe failure must not gate sign-in; fall back to the safe shape.
        if (active) setState({ ...FALLBACK, loading: false })
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [])

  return state
}
