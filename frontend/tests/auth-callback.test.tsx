/**
 * The sign-in link landing page.
 *
 * Regression cover for a real failure: clicking a valid link bounced straight
 * back to /login because the page decided "anonymous" before Supabase had
 * finished exchanging the credential in the URL. It must wait.
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
  window.history.replaceState({}, '', '/auth/callback')
  getSession.mockResolvedValue({ data: { session: null } })
  onAuthStateChange.mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
})

afterEach(() => {
  vi.useRealTimers()
})

async function renderCallback() {
  const { AuthProvider } = await import('@/features/auth/AuthProvider')
  const { AuthCallbackPage } = await import('@/features/auth/AuthCallbackPage')
  const { MemoryRouter } = await import('react-router-dom')

  return render(
    <MemoryRouter initialEntries={['/auth/callback']}>
      <AuthProvider>
        <AuthCallbackPage />
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('sign-in link callback', () => {
  it('waits instead of bouncing to login while the exchange is in flight', async () => {
    // The exact shape of the bug: not signed in *yet*.
    const { ApiRequestError } = await import('@/lib/api-client')
    mockGet.mockRejectedValue(
      new ApiRequestError(401, { code: 'unauthenticated', message: 'no token' }),
    )

    await renderCallback()

    await waitFor(() => {
      expect(screen.getByText(/Signing you in/i)).toBeInTheDocument()
    })
    // Must NOT have given up yet.
    expect(screen.queryByText(/Could not complete sign-in/i)).not.toBeInTheDocument()
  })

  it('surfaces an error carried in the URL query string', async () => {
    window.history.replaceState(
      {},
      '',
      '/auth/callback?error=access_denied&error_description=Email+link+is+invalid+or+has+expired',
    )
    mockGet.mockResolvedValue({})

    await renderCallback()

    await waitFor(() => {
      expect(screen.getByText(/Could not complete sign-in/i)).toBeInTheDocument()
    })
    expect(
      screen.getByText(/Email link is invalid or has expired/i),
    ).toBeInTheDocument()
  })

  it('surfaces an error carried in the URL hash fragment', async () => {
    window.history.replaceState(
      {},
      '',
      '/auth/callback#error=access_denied&error_description=Token+has+expired',
    )
    mockGet.mockResolvedValue({})

    await renderCallback()

    await waitFor(() => {
      expect(screen.getByText(/Token has expired/i)).toBeInTheDocument()
    })
  })

  it('holds the guard when a link lands on the protected root, not /auth/callback', async () => {
    // Supabase redirects sign-in links to its Site URL, which is the app root
    // — a protected route. Before the fix, ProtectedRoute saw "anonymous" and
    // redirected to /login while the credential in the URL was still being
    // exchanged, so a valid link appeared to do nothing.
    window.history.replaceState({}, '', '/?code=pkce-authorization-code')
    const { ApiRequestError } = await import('@/lib/api-client')
    mockGet.mockRejectedValue(
      new ApiRequestError(401, { code: 'unauthenticated', message: 'no token' }),
    )

    const { ProtectedRoute } = await import('@/features/auth/ProtectedRoute')
    const { AuthProvider } = await import('@/features/auth/AuthProvider')
    const { MemoryRouter, Route, Routes } = await import('react-router-dom')

    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <Routes>
            <Route element={<ProtectedRoute />}>
              <Route path="/" element={<div>DASHBOARD</div>} />
            </Route>
            <Route path="/login" element={<div>LOGIN PAGE</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText(/Checking your session/i)).toBeInTheDocument()
    })
    expect(screen.queryByText('LOGIN PAGE')).not.toBeInTheDocument()
  })

  it('explains the same-browser requirement after giving up', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const { ApiRequestError } = await import('@/lib/api-client')
    mockGet.mockRejectedValue(
      new ApiRequestError(401, { code: 'unauthenticated', message: 'no token' }),
    )

    await renderCallback()
    await vi.advanceTimersByTimeAsync(9000)

    await waitFor(() => {
      expect(screen.getByText(/same browser that requested them/i)).toBeInTheDocument()
    })
  })
})
