/**
 * When the login screen is allowed to appear.
 *
 * Regression cover for a deployment-only failure: the provider waited on the
 * `/auth/me` probe before deciding anything, so a cold-starting backend — ~50
 * seconds on a free host — kept the login page behind a spinner. It worked
 * locally because a local API answers instantly.
 *
 * The rule: with no session the visitor is known to be anonymous, so the login
 * page must render without waiting for any network call.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type * as ApiClientModule from '@/lib/api-client'

const { getSession, onAuthStateChange } = vi.hoisted(() => ({
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
      signInWithOtp: vi.fn(),
      verifyOtp: vi.fn(),
      signInWithOAuth: vi.fn(),
      signOut: vi.fn(),
    },
  },
}))

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof ApiClientModule>()
  return { ...actual, api: { get: mockGet, post: vi.fn(), patch: vi.fn(), delete: vi.fn() } }
})

beforeEach(() => {
  vi.clearAllMocks()
  window.history.replaceState({}, '', '/login')
  onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      new Response(JSON.stringify({ external: { email: true, google: true } }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  )
})

afterEach(() => {
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
}

describe('when the login screen appears', () => {
  it('renders immediately when no session exists, even if the API never answers', async () => {
    getSession.mockResolvedValue({ data: { session: null } })
    // The cold-start case: the request simply never settles.
    mockGet.mockReturnValue(new Promise(() => {}))

    await renderLogin()

    await waitFor(() => {
      expect(screen.getByLabelText(/Email address/i)).toBeInTheDocument()
    })
    expect(
      screen.getByRole('button', { name: /Send me a sign-in email/i }),
    ).toBeInTheDocument()
  })

  it('offers Google without waiting for the backend', async () => {
    getSession.mockResolvedValue({ data: { session: null } })
    mockGet.mockReturnValue(new Promise(() => {}))

    await renderLogin()

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: /Continue with Google/i }),
      ).toBeInTheDocument()
    })
  })

  it('does wait for the profile when a session exists', async () => {
    // Here the answer is genuinely unknown until the API replies, so showing
    // the login form would be wrong — the user may already be signed in.
    getSession.mockResolvedValue({
      data: { session: { access_token: 't', user: { id: 'u' } } },
    })
    mockGet.mockReturnValue(new Promise(() => {}))

    await renderLogin()

    await waitFor(() => {
      expect(screen.getByText(/Checking your session/i)).toBeInTheDocument()
    })
    expect(screen.queryByLabelText(/Email address/i)).not.toBeInTheDocument()
  })
})
