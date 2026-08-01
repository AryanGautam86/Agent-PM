/**
 * Smoke test: the application actually mounts.
 *
 * Typechecking and building both passed while the app rendered a blank page,
 * because the failure was a runtime throw at module load. Nothing short of
 * executing the code catches that, so this test mounts the real route table
 * inside the real providers and asserts that something reaches the DOM.
 *
 * The API client is mocked rather than `fetch`, because react-router builds
 * its own `Request` objects and a global fetch stub collides with jsdom.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type * as ApiClientModule from '@/lib/api-client'

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof ApiClientModule>()
  return {
    ...actual,
    api: { get: mockGet, post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  }
})

beforeEach(() => {
  mockGet.mockReset()
  // No Supabase configured — the exact state the app was blank in.
  vi.stubEnv('VITE_SUPABASE_URL', '')
  vi.stubEnv('VITE_SUPABASE_ANON_KEY', '')
})

afterEach(() => {
  vi.unstubAllEnvs()
})

async function renderApp(initialPath = '/') {
  const { createMemoryRouter, RouterProvider } = await import('react-router-dom')
  const { Providers } = await import('@/app/providers')
  const { routes } = await import('@/app/router')

  const router = createMemoryRouter(routes, { initialEntries: [initialPath] })
  return render(
    <Providers>
      <RouterProvider router={router} />
    </Providers>,
  )
}

async function anonymous() {
  const { ApiRequestError } = await import('@/lib/api-client')
  mockGet.mockRejectedValue(
    new ApiRequestError(401, {
      code: 'unauthenticated',
      message: 'Missing Authorization header',
    }),
  )
}

describe('application mount', () => {
  // Mounted at /login rather than / on purpose: the guard's redirect makes
  // react-router build a Request, which jsdom's AbortSignal cannot satisfy.
  // The redirect itself is the guard's job and is covered by its own test;
  // what matters here is that the page renders at all.
  it('renders the sign-in screen', async () => {
    await anonymous()

    await renderApp('/login')

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Agent-PM' })).toBeInTheDocument()
    })
    expect(screen.getByText(/Continue with Google/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/Email address/i)).toBeInTheDocument()
  })

  it('says sign-in is unavailable when Supabase is not configured', async () => {
    await anonymous()

    await renderApp('/login')

    await waitFor(() => {
      expect(screen.getByText(/Sign-in is not configured yet/i)).toBeInTheDocument()
    })
    // The instructions must name what to set, not just report a problem.
    expect(screen.getByText('VITE_SUPABASE_URL')).toBeInTheDocument()
  })

  it('offers the one-time-code flow as well as Google', async () => {
    await anonymous()

    await renderApp('/login')

    await waitFor(() => {
      expect(screen.getByText(/Send me a sign-in email/i)).toBeInTheDocument()
    })
  })

  it('renders the app shell when the backend authenticates the caller', async () => {
    // The dev-bypass shape: /auth/me answers without a token.
    mockGet.mockImplementation(async (path: string) => {
      if (path === '/auth/me') {
        return {
          id: '00000000-0000-0000-0000-000000000001',
          email: 'dev@example.com',
          full_name: 'Dev User',
          avatar_url: null,
          role: 'admin',
          auth_provider: 'dev-bypass',
          is_active: true,
        }
      }
      return []
    })

    await renderApp()

    await waitFor(() => {
      expect(screen.getByText('Delivery Steward')).toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: /Standups/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Tasks/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Reports/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Team/ })).toBeInTheDocument()
  })
})
