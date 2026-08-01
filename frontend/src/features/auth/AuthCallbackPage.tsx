/**
 * Landing page for the email sign-in link and the Google OAuth redirect.
 *
 * The Supabase client parses the credential out of the URL on load, but that
 * is asynchronous. An earlier version simply watched auth status and sent
 * anyone "anonymous" back to /login — which fired *before* the exchange
 * finished, so clicking a perfectly valid sign-in link just bounced the user
 * to the login page and looked like nothing had happened.
 *
 * So this page waits. It only gives up after a grace period, and when it does
 * it explains why instead of silently redirecting.
 */

import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Spinner } from '@/components/ui/Spinner'
import { useAuth } from '@/features/auth/useAuth'

/** Long enough for a slow network round-trip, short enough not to feel stuck. */
const GRACE_PERIOD_MS = 8000

function errorFromUrl(): string | null {
  // Supabase reports failures in the query string for PKCE and in the hash
  // fragment for the implicit flow, so both have to be checked.
  const search = new URLSearchParams(window.location.search)
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''))
  const description =
    search.get('error_description') ?? hash.get('error_description')
  const code = search.get('error') ?? hash.get('error')
  if (!description && !code) return null
  return (description ?? code ?? '').replace(/\+/g, ' ')
}

export function AuthCallbackPage() {
  const { status, error } = useAuth()
  const navigate = useNavigate()
  const [gaveUp, setGaveUp] = useState(false)
  const [urlError] = useState(errorFromUrl)

  useEffect(() => {
    if (status === 'authenticated') {
      navigate('/', { replace: true })
    }
  }, [status, navigate])

  useEffect(() => {
    if (urlError) return
    const timer = setTimeout(() => setGaveUp(true), GRACE_PERIOD_MS)
    return () => clearTimeout(timer)
  }, [urlError])

  const failure = urlError ?? error

  if (failure || (gaveUp && status !== 'authenticated')) {
    return (
      <div className="auth-shell">
        <div className="auth-card">
          <h1>Could not complete sign-in</h1>
          {failure ? (
            <p className="alert alert-error">{failure}</p>
          ) : (
            <p className="alert alert-warning">
              The link did not carry a valid session.
              <span className="alert-hint">
                Sign-in links are single use and expire after an hour. They also
                have to be opened in the same browser that requested them — the
                security check is stored there.
              </span>
            </p>
          )}
          <Link className="link" to="/login">
            Back to sign in
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="center-screen">
      <Spinner label="Signing you in" />
    </div>
  )
}
