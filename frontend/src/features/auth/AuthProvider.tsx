/**
 * Authentication context.
 *
 * Supabase owns the session. This provider mirrors it into React state and
 * exposes the two sign-in methods the product uses: Google OAuth and email
 * OTP. It also calls `GET /auth/me` once a session exists, which is what
 * provisions the backend profile row.
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'

import { AuthContext, type AuthContextValue } from '@/features/auth/auth-context'
import { api, ApiRequestError, setUnauthorizedHandler } from '@/lib/api-client'
import { authRedirectUrl, supabase } from '@/lib/supabase'
import type { CurrentUser } from '@/types/api'

/** How long to wait for Supabase to turn a URL credential into a session. */
const URL_AUTH_GRACE_MS = 8000

/**
 * Does the current URL look like an auth callback?
 *
 * PKCE returns `?code=`, the implicit flow returns `#access_token=`, and
 * failures arrive as `error`/`error_description` in either place. Any of them
 * means a sign-in attempt is in progress and the guard must hold off.
 */
function hasAuthCredentialInUrl(): boolean {
  if (typeof window === 'undefined') return false
  const search = new URLSearchParams(window.location.search)
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''))
  return ['code', 'access_token', 'error', 'error_description'].some(
    (key) => search.has(key) || hash.has(key),
  )
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [ready, setReady] = useState(false)
  const [profileLoading, setProfileLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // True when the current URL carries a credential Supabase is still turning
  // into a session. Sign-in links land on whatever Supabase's Site URL is —
  // often "/", which is a protected route — so without this the guard sees
  // "anonymous" and redirects to /login before the exchange finishes. The user
  // clicks a valid link and lands back on the login page.
  const [resolvingUrlAuth, setResolvingUrlAuth] = useState(hasAuthCredentialInUrl)

  // Mirror the Supabase session into state.
  useEffect(() => {
    let active = true

    supabase.auth.getSession().then(({ data }) => {
      if (!active) return
      setSession(data.session)
      setReady(true)
    })

    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession)
      setReady(true)
    })

    return () => {
      active = false
      data.subscription.unsubscribe()
    }
  }, [])

  // Sync the backend profile.
  //
  // Attempted even with no Supabase session, because the backend may be
  // running with the local dev bypass, in which case it answers without a
  // token. In the normal case this is one 401 on first load, which is what
  // tells us the visitor is anonymous.
  useEffect(() => {
    let active = true
    setProfileLoading(true)

    api
      .get<CurrentUser>('/auth/me')
      .then((profile) => {
        if (!active) return
        setUser(profile)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!active) return
        setUser(null)
        // Only surface an error when we *had* a session: a 401 with no
        // session is simply "not signed in", not a failure worth showing.
        const isUnauthorized =
          err instanceof ApiRequestError && err.isAuthError
        setError(
          session && !isUnauthorized
            ? err instanceof Error
              ? err.message
              : 'Could not load your profile'
            : null,
        )
      })
      .finally(() => {
        if (active) setProfileLoading(false)
      })

    return () => {
      active = false
    }
  }, [session])

  const signInWithGoogle = useCallback(async () => {
    setError(null)
    const { error: oauthError } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: authRedirectUrl(),
        queryParams: { prompt: 'select_account' },
      },
    })
    if (oauthError) throw new Error(oauthError.message)
  }, [])

  const sendEmailOtp = useCallback(async (email: string) => {
    setError(null)
    const { error: otpError } = await supabase.auth.signInWithOtp({
      email,
      options: {
        // The user types the code rather than following a link, so no
        // redirect is involved. `shouldCreateUser` lets a new teammate in
        // without an invite step.
        shouldCreateUser: true,
        emailRedirectTo: authRedirectUrl(),
      },
    })
    if (otpError) throw new Error(otpError.message)
  }, [])

  const verifyEmailOtp = useCallback(async (email: string, token: string) => {
    setError(null)
    const { error: verifyError } = await supabase.auth.verifyOtp({
      email,
      token: token.trim(),
      type: 'email',
    })
    if (verifyError) throw new Error(verifyError.message)
  }, [])

  const signOut = useCallback(async () => {
    await supabase.auth.signOut()
    setUser(null)
    setSession(null)
  }, [])

  // End the session when the API says the caller is no longer authenticated.
  // Guarded on `session` so the anonymous /auth/me probe — which is expected
  // to 401 — cannot trigger a sign-out loop.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (!session) return
      setUser(null)
      setError('Your session expired. Sign in again.')
      void supabase.auth.signOut()
    })
    return () => setUnauthorizedHandler(null)
  }, [session])

  // Stop waiting once a session appears, or after a bounded grace period so a
  // malformed link cannot leave the app spinning forever.
  useEffect(() => {
    if (!resolvingUrlAuth) return
    if (session) {
      setResolvingUrlAuth(false)
      return
    }
    const timer = setTimeout(() => setResolvingUrlAuth(false), URL_AUTH_GRACE_MS)
    return () => clearTimeout(timer)
  }, [resolvingUrlAuth, session])

  const value = useMemo<AuthContextValue>(() => {
    // Waiting on the profile probe is only justified when a session exists.
    //
    // With no session the answer is already known — the visitor is anonymous —
    // and blocking on the API means a cold-starting backend hides the login
    // page behind a spinner. On a free host that is ~50 seconds of looking
    // broken. The probe still runs, and flips this to authenticated if the
    // server recognises the caller anyway (the local dev bypass).
    const status: AuthContextValue['status'] =
      !ready || resolvingUrlAuth
        ? 'loading'
        : user
          ? 'authenticated'
          : session && profileLoading
            ? 'loading'
            : 'anonymous'

    return {
      session,
      user,
      status,
      error,
      signInWithGoogle,
      sendEmailOtp,
      verifyEmailOtp,
      signOut,
    }
  }, [
    ready,
    profileLoading,
    resolvingUrlAuth,
    session,
    user,
    error,
    signInWithGoogle,
    sendEmailOtp,
    verifyEmailOtp,
    signOut,
  ])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
