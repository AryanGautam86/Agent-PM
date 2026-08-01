/**
 * Sign-in.
 *
 * Email one-time code is the primary path and Google is the alternative.
 * Phone/SMS is deliberately absent: Supabase does not send SMS itself, so it
 * would mean a paid Twilio-style provider and a purchased sender number for no
 * gain over email.
 *
 * The two OTP steps live in one component rather than two routes, because
 * splitting them loses the email address on refresh and makes "resend"
 * awkward to reason about.
 */

import { useEffect, useRef, useState, type ClipboardEvent, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { friendlyAuthError, type FriendlyAuthError } from '@/features/auth/auth-errors'
import { useAuth } from '@/features/auth/useAuth'
import { useAuthProviders } from '@/features/auth/useAuthProviders'
import { useResendCooldown } from '@/features/auth/useResendCooldown'
import { isSupabaseConfigured } from '@/lib/supabase'

const CODE_LENGTH = 6

type Stage = 'email' | 'code'

export function LoginPage() {
  const { status, signInWithGoogle, sendEmailOtp, verifyEmailOtp } = useAuth()

  const [stage, setStage] = useState<Stage>('email')
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<FriendlyAuthError | null>(null)

  const providers = useAuthProviders()
  const cooldown = useResendCooldown(60)
  const codeInput = useRef<HTMLInputElement>(null)
  const submittedFor = useRef<string | null>(null)

  useEffect(() => {
    if (stage === 'code') codeInput.current?.focus()
  }, [stage])

  // Submit as soon as six digits are present, so nobody has to hunt for a
  // button after typing or pasting the code. Guarded against re-submitting the
  // same value if verification fails.
  useEffect(() => {
    if (
      stage === 'code' &&
      code.length === CODE_LENGTH &&
      !busy &&
      submittedFor.current !== code
    ) {
      submittedFor.current = code
      void verify()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, stage, busy])

  if (status === 'authenticated') {
    return <Navigate to="/" replace />
  }

  if (status === 'loading') {
    return (
      <div className="auth-shell">
        <Spinner label="Checking your session" />
      </div>
    )
  }

  async function run(action: () => Promise<void>, onDone?: () => void) {
    setBusy(true)
    setError(null)
    try {
      await action()
      onDone?.()
      return true
    } catch (err) {
      const friendly = friendlyAuthError(err)
      setError(friendly)
      if (friendly.restart) {
        setCode('')
        submittedFor.current = null
      }
      // A rate-limited send is not a dead end: an earlier code may still be
      // valid, and the limit is per project, so a user can hit it without
      // having done anything. Let them through to enter one.
      if (friendly.rateLimited) {
        goToCodeStage()
      }
      return false
    } finally {
      setBusy(false)
    }
  }

  function goToCodeStage() {
    setStage('code')
    setCode('')
    submittedFor.current = null
  }

  function sendCode(event?: FormEvent) {
    event?.preventDefault()
    const address = email.trim().toLowerCase()
    if (!address) return
    void run(
      () => sendEmailOtp(address),
      () => {
        goToCodeStage()
        cooldown.start()
      },
    )
  }

  function verify() {
    return run(() => verifyEmailOtp(email.trim().toLowerCase(), code))
  }

  function handlePaste(event: ClipboardEvent<HTMLInputElement>) {
    // Mail clients often copy the code with surrounding whitespace.
    const digits = event.clipboardData.getData('text').replace(/\D/g, '')
    if (digits) {
      event.preventDefault()
      setCode(digits.slice(0, CODE_LENGTH))
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="auth-mark" aria-hidden="true">
            PM
          </span>
          <div>
            <h1>Agent-PM</h1>
            <p className="muted">Delivery Steward</p>
          </div>
        </div>

        {!isSupabaseConfigured && <NotConfigured />}

        {error && (
          <div className="alert alert-error" role="alert">
            {error.message}
            {error.hint && <div className="alert-hint">{error.hint}</div>}
          </div>
        )}

        {stage === 'email' ? (
          <>
            {providers.google ? (
              <Button
                onClick={() => void run(() => signInWithGoogle())}
                disabled={busy || !isSupabaseConfigured}
                full
              >
                <GoogleMark />
                Continue with Google
              </Button>
            ) : (
              <div className="provider-disabled">
                <span className="provider-disabled-row">
                  <GoogleMark />
                  Continue with Google
                </span>
                <span className="muted">
                  Not enabled on this project yet. An administrator can turn it
                  on under Authentication → Providers → Google.
                </span>
              </div>
            )}

            <div className="auth-divider">
              <span>or use your email</span>
            </div>

            <form onSubmit={sendCode} className="auth-form">
              <label htmlFor="email">Email address</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                autoFocus
                required
                placeholder="you@company.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                disabled={busy || !isSupabaseConfigured}
              />
              <Button
                type="submit"
                variant="primary"
                loading={busy}
                disabled={!email.trim() || !isSupabaseConfigured}
                full
              >
                Send me a sign-in email
              </Button>
              <p className="muted auth-note">
                The email contains a sign-in link and, where enabled, a{' '}
                {CODE_LENGTH}-digit code. Either one signs you in.
              </p>
            </form>

            <div className="auth-actions">
              <button
                type="button"
                className="link"
                onClick={() => {
                  if (!email.trim()) {
                    setError({ message: 'Enter your email address first.' })
                    return
                  }
                  setError(null)
                  goToCodeStage()
                }}
                disabled={busy}
              >
                I already have a code
              </button>
            </div>
          </>
        ) : (
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void verify()
            }}
            className="auth-form"
          >
            <p>
              We sent an email to <strong>{email}</strong>.
            </p>

            {/*
              Supabase's free tier with the default email sender does not allow
              editing templates, so the message contains a sign-in LINK rather
              than digits. Both paths are offered: the link works today, the
              code works once custom SMTP is configured.
            */}
            <div className="alert alert-info">
              <strong>Click the sign-in link in that email.</strong>
              <div className="alert-hint">
                Open it in <em>this</em> browser — the security check that
                completes sign-in is stored here. If your email shows a
                {' '}{CODE_LENGTH}-digit code instead, type it below.
              </div>
            </div>

            <label htmlFor="code">Or enter the code, if you got one</label>
            <input
              id="code"
              ref={codeInput}
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]*"
              maxLength={CODE_LENGTH}
              required
              placeholder="123456"
              className="otp-input"
              value={code}
              onPaste={handlePaste}
              onChange={(event) =>
                setCode(event.target.value.replace(/\D/g, '').slice(0, CODE_LENGTH))
              }
              disabled={busy}
            />

            <Button
              type="submit"
              variant="primary"
              loading={busy}
              disabled={code.length < CODE_LENGTH}
              full
            >
              Verify and sign in
            </Button>

            <div className="auth-actions">
              <button
                type="button"
                className="link"
                onClick={() => sendCode()}
                disabled={busy || cooldown.active}
              >
                {cooldown.active ? `Resend in ${cooldown.remaining}s` : 'Resend code'}
              </button>
              <button
                type="button"
                className="link"
                onClick={() => {
                  setStage('email')
                  setCode('')
                  setError(null)
                  submittedFor.current = null
                }}
                disabled={busy}
              >
                Use a different email
              </button>
            </div>

            <p className="auth-footnote muted">
              Not arrived? Check spam. Links and codes expire after an hour.
            </p>
          </form>
        )}

        <p className="auth-footnote muted">
          {providers.signupsOpen
            ? 'Anyone can sign in — an account is created automatically the first time.'
            : 'Sign-ups are closed on this project; ask an administrator to invite you.'}{' '}
          If you see no engagements afterwards, ask an administrator to add you
          to a pod.
        </p>
      </div>
    </div>
  )
}

function NotConfigured() {
  return (
    <div className="alert alert-warning">
      <strong>Sign-in is not configured yet.</strong>
      <div className="alert-hint">
        Add <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_ANON_KEY</code>{' '}
        to <code>frontend/.env.local</code>, then restart the dev server. For
        codes to arrive as digits rather than a link, the Supabase{' '}
        <em>Magic Link</em> email template must contain{' '}
        <code>{'{{ .Token }}'}</code>.
      </div>
    </div>
  )
}

function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.94v2.33A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.41 5.41 0 0 1 0-3.44V4.95H.94a9 9 0 0 0 0 8.1l3.03-2.33Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .94 4.95l3.03 2.33C4.68 5.16 6.66 3.58 9 3.58Z"
      />
    </svg>
  )
}
