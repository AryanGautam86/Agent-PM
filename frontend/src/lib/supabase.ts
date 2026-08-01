/**
 * Supabase client — authentication only.
 *
 * The SPA never queries tables directly; all data goes through the API so that
 * grounding, autonomy gating and audit cannot be bypassed. This client exists
 * to run Google OAuth and email OTP and to hold the session.
 */

import { createClient, type SupabaseClient } from '@supabase/supabase-js'

// Trimmed and coerced with `||`, not `??`: an unset variable in a .env file
// arrives as an EMPTY STRING, not undefined. `??` would pass '' straight to
// createClient, which throws "supabaseUrl is required" at module load — and a
// throw here means React never mounts and the whole app renders blank.
const url = (import.meta.env.VITE_SUPABASE_URL ?? '').trim()
const anonKey = (import.meta.env.VITE_SUPABASE_ANON_KEY ?? '').trim()

export const isSupabaseConfigured = Boolean(url && anonKey)

/** Exported so the login page can ask the project which providers are live. */
export const supabaseUrl = url
export const supabaseAnonKey = anonKey

if (!isSupabaseConfigured && import.meta.env.DEV) {
  console.warn(
    '[agent-pm] VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY are not set. ' +
      'Sign-in is unavailable; the app works only if the backend has ' +
      'DEV_AUTH_BYPASS_EMAIL set. See frontend/.env.example.',
  )
}

// A syntactically valid placeholder keeps the client constructible when
// Supabase is not configured. It is never called in that state — the backend
// bypass answers /auth/me — but getSession() must not explode on load.
export const supabase: SupabaseClient = createClient(
  url || 'https://placeholder.supabase.co',
  anonKey || 'placeholder-anon-key',
  {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      // Required for the OAuth redirect: the tokens come back in the URL hash
      // and the client has to pick them up on load.
      detectSessionInUrl: true,
      flowType: 'pkce',
    },
  },
)

/** Where Supabase should send the browser back to after Google sign-in. */
export function authRedirectUrl(): string {
  return `${window.location.origin}/auth/callback`
}
