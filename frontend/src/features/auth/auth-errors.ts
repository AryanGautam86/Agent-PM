/**
 * Turns Supabase auth errors into something a person can act on.
 *
 * The raw messages are written for developers ("Token has expired or is
 * invalid") and several distinct failures share wording, so a plain
 * pass-through leaves users stuck. Each case below maps to the action that
 * actually resolves it.
 */

export interface FriendlyAuthError {
  message: string
  hint?: string
  /** True when the user should go back and re-request a code. */
  restart?: boolean
  /**
   * True when the send was refused for rate limiting rather than rejected.
   * A previously delivered code may still be valid, so the UI should let the
   * user reach the code entry screen instead of stranding them.
   */
  rateLimited?: boolean
}

const OTP_EXPIRED = /token has expired|invalid.*token|otp_expired/i
const RATE_LIMITED = /rate limit|too many requests|for security purposes/i
const INVALID_EMAIL = /invalid.*email|unable to validate email/i
const SIGNUPS_DISABLED = /signups not allowed|signup is disabled/i
const NOT_CONFIGURED = /supabaseurl is required|failed to fetch|networkerror/i

export function friendlyAuthError(error: unknown): FriendlyAuthError {
  const raw = error instanceof Error ? error.message : String(error ?? '')

  if (NOT_CONFIGURED.test(raw)) {
    return {
      message: 'Cannot reach the authentication service.',
      hint:
        'Check VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in ' +
        'frontend/.env.local, then restart the dev server.',
    }
  }

  if (RATE_LIMITED.test(raw)) {
    return {
      message: 'No new email could be sent just now — the hourly limit is reached.',
      hint:
        'This limit is per project, not per person, so it can be hit by ' +
        'someone else or by an earlier attempt. If you already received a ' +
        'code, it is still valid — enter it below.',
      rateLimited: true,
    }
  }

  if (OTP_EXPIRED.test(raw)) {
    return {
      message: 'That code is wrong or has expired.',
      hint: 'Codes last about an hour. Request a new one.',
      restart: true,
    }
  }

  if (INVALID_EMAIL.test(raw)) {
    return { message: 'That email address does not look valid.' }
  }

  if (SIGNUPS_DISABLED.test(raw)) {
    return {
      message: 'This address is not allowed to sign in.',
      hint: 'Sign-ups are disabled on the Supabase project. Ask an admin to invite you.',
    }
  }

  return { message: raw || 'Something went wrong. Try again.' }
}
