/**
 * The email one-time-code sign-in flow.
 *
 * Supabase is mocked at the client boundary, so these cover our behaviour —
 * the two-step flow, auto-submit, paste handling, resend gating and error
 * mapping — rather than the provider's.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type * as ApiClientModule from '@/lib/api-client'

const { signInWithOtp, verifyOtp, signInWithOAuth, getSession, onAuthStateChange } =
  vi.hoisted(() => ({
    signInWithOtp: vi.fn(),
    verifyOtp: vi.fn(),
    signInWithOAuth: vi.fn(),
    getSession: vi.fn(),
    onAuthStateChange: vi.fn(),
  }))

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))

vi.mock('@/lib/supabase', () => ({
  isSupabaseConfigured: true,
  supabaseUrl: 'https://example.supabase.co',
  supabaseAnonKey: 'sb_publishable_test',
  authRedirectUrl: () => 'http://localhost:5173/auth/callback',
  supabase: {
    auth: {
      getSession,
      onAuthStateChange,
      signInWithOtp,
      verifyOtp,
      signInWithOAuth,
      signOut: vi.fn(),
    },
  },
}))

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof ApiClientModule>()
  return { ...actual, api: { get: mockGet, post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }
})

/** Stubs the public /auth/v1/settings probe the login page makes. */
function providersEnabled(external: Record<string, boolean>, disableSignup = false) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      new Response(JSON.stringify({ external, disable_signup: disableSignup }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
}

beforeEach(async () => {
  vi.clearAllMocks()
  providersEnabled({ email: true, google: false })
  getSession.mockResolvedValue({ data: { session: null } })
  onAuthStateChange.mockReturnValue({
    data: { subscription: { unsubscribe: vi.fn() } },
  })
  signInWithOtp.mockResolvedValue({ error: null })
  verifyOtp.mockResolvedValue({ error: null })
  signInWithOAuth.mockResolvedValue({ error: null })

  const { ApiRequestError } = await import('@/lib/api-client')
  mockGet.mockRejectedValue(
    new ApiRequestError(401, { code: 'unauthenticated', message: 'no token' }),
  )
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

async function renderLogin() {
  const { AuthProvider } = await import('@/features/auth/AuthProvider')
  const { LoginPage } = await import('@/features/auth/LoginPage')
  const { MemoryRouter } = await import('react-router-dom')

  render(
    <MemoryRouter>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>,
  )

  await screen.findByLabelText(/Email address/i)
}

describe('email one-time-code sign-in', () => {
  it('sends a code to the address entered', async () => {
    const user = userEvent.setup()
    await renderLogin()

    await user.type(screen.getByLabelText(/Email address/i), 'Aryan.G@Example.com')
    await user.click(screen.getByRole('button', { name: /Send me a sign-in email/i }))

    await waitFor(() => expect(signInWithOtp).toHaveBeenCalledTimes(1))
    // Normalised: the same person typing different casing must not create two
    // accounts.
    expect(signInWithOtp).toHaveBeenCalledWith(
      expect.objectContaining({ email: 'aryan.g@example.com' }),
    )
  })

  it('moves to the code step and shows where it went', async () => {
    const user = userEvent.setup()
    await renderLogin()

    await user.type(screen.getByLabelText(/Email address/i), 'a@b.com')
    await user.click(screen.getByRole('button', { name: /Send me a sign-in email/i }))

    expect(await screen.findByLabelText(/Enter the code/i)).toBeInTheDocument()
    expect(screen.getByText('a@b.com')).toBeInTheDocument()
  })

  it('verifies automatically once six digits are entered', async () => {
    const user = userEvent.setup()
    await renderLogin()

    await user.type(screen.getByLabelText(/Email address/i), 'a@b.com')
    await user.click(screen.getByRole('button', { name: /Send me a sign-in email/i }))
    await user.type(await screen.findByLabelText(/Enter the code/i), '123456')

    await waitFor(() =>
      expect(verifyOtp).toHaveBeenCalledWith(
        expect.objectContaining({ email: 'a@b.com', token: '123456', type: 'email' }),
      ),
    )
  })

  it('strips non-digits, so a pasted code with spaces still works', async () => {
    const user = userEvent.setup()
    await renderLogin()

    await user.type(screen.getByLabelText(/Email address/i), 'a@b.com')
    await user.click(screen.getByRole('button', { name: /Send me a sign-in email/i }))

    const input = await screen.findByLabelText(/Enter the code/i)
    await user.click(input)
    await user.paste('12 34-56')

    await waitFor(() =>
      expect(verifyOtp).toHaveBeenCalledWith(
        expect.objectContaining({ token: '123456' }),
      ),
    )
  })

  it('blocks resend behind a countdown', async () => {
    const user = userEvent.setup()
    await renderLogin()

    await user.type(screen.getByLabelText(/Email address/i), 'a@b.com')
    await user.click(screen.getByRole('button', { name: /Send me a sign-in email/i }))

    const resend = await screen.findByRole('button', { name: /Resend in \d+s/ })
    expect(resend).toBeDisabled()
  })

  it('explains an expired code instead of repeating the raw error', async () => {
    verifyOtp.mockResolvedValue({
      error: { message: 'Token has expired or is invalid' },
    })
    const user = userEvent.setup()
    await renderLogin()

    await user.type(screen.getByLabelText(/Email address/i), 'a@b.com')
    await user.click(screen.getByRole('button', { name: /Send me a sign-in email/i }))
    await user.type(await screen.findByLabelText(/Enter the code/i), '000000')

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /code is wrong or has expired/i,
    )
  })

  it('does not strand the user when the send is rate limited', async () => {
    // The project-wide hourly cap can be hit by someone else entirely. An
    // already-delivered code may still be valid, so the code entry screen must
    // still be reachable — otherwise the user is stuck with no way forward.
    signInWithOtp.mockResolvedValue({
      error: { message: 'For security purposes, you can only request this after 51s' },
    })
    const user = userEvent.setup()
    await renderLogin()

    await user.type(screen.getByLabelText(/Email address/i), 'a@b.com')
    await user.click(screen.getByRole('button', { name: /Send me a sign-in email/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/hourly limit is reached/i)
    expect(await screen.findByLabelText(/enter the code/i)).toBeInTheDocument()
  })

  it('lets someone who already has a code skip the send entirely', async () => {
    const user = userEvent.setup()
    await renderLogin()

    await user.type(screen.getByLabelText(/Email address/i), 'a@b.com')
    await user.click(screen.getByRole('button', { name: /already have a code/i }))

    expect(await screen.findByLabelText(/enter the code/i)).toBeInTheDocument()
    // Nothing was sent — the whole point.
    expect(signInWithOtp).not.toHaveBeenCalled()
  })

  it('asks for the email first if the skip link is used with an empty field', async () => {
    const user = userEvent.setup()
    await renderLogin()

    await user.click(screen.getByRole('button', { name: /already have a code/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/Enter your email address first/i)
  })

  it('lets the user go back and correct the address', async () => {
    const user = userEvent.setup()
    await renderLogin()

    await user.type(screen.getByLabelText(/Email address/i), 'wrong@b.com')
    await user.click(screen.getByRole('button', { name: /Send me a sign-in email/i }))
    await user.click(await screen.findByRole('button', { name: /different email/i }))

    expect(await screen.findByLabelText(/Email address/i)).toBeInTheDocument()
  })

  it('offers Google when the project has it enabled', async () => {
    providersEnabled({ email: true, google: true })
    const user = userEvent.setup()
    await renderLogin()

    const google = await screen.findByRole('button', { name: /Continue with Google/i })
    await user.click(google)

    await waitFor(() =>
      expect(signInWithOAuth).toHaveBeenCalledWith(
        expect.objectContaining({ provider: 'google' }),
      ),
    )
  })

  it('explains Google rather than offering a button that fails', async () => {
    providersEnabled({ email: true, google: false })
    await renderLogin()

    await waitFor(() =>
      expect(screen.getByText(/Not enabled on this project yet/i)).toBeInTheDocument(),
    )
    // No clickable Google button when it cannot work.
    expect(
      screen.queryByRole('button', { name: /Continue with Google/i }),
    ).not.toBeInTheDocument()
  })

  it('says anyone can sign in when sign-ups are open', async () => {
    providersEnabled({ email: true, google: false }, false)
    await renderLogin()

    await waitFor(() =>
      expect(screen.getByText(/Anyone can sign in/i)).toBeInTheDocument(),
    )
  })

  it('says sign-ups are closed when the project disables them', async () => {
    providersEnabled({ email: true, google: false }, true)
    await renderLogin()

    await waitFor(() =>
      expect(screen.getByText(/Sign-ups are closed/i)).toBeInTheDocument(),
    )
  })

  it('still works if the provider probe fails entirely', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new Error('offline'))))
    const user = userEvent.setup()
    await renderLogin()

    // A failed probe must not gate the primary path: email stays usable.
    await user.type(screen.getByLabelText(/Email address/i), 'a@b.com')
    await user.click(screen.getByRole('button', { name: /Send me a sign-in email/i }))

    await waitFor(() => expect(signInWithOtp).toHaveBeenCalledTimes(1))
  })
})
