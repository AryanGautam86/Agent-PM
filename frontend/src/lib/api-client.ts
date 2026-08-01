/**
 * Typed fetch wrapper.
 *
 * Every request carries the current Supabase access token. The token is read
 * from the session at call time rather than captured once, so a refresh in the
 * background is picked up without re-rendering anything.
 */

import { supabase } from '@/lib/supabase'
import type { ApiError } from '@/types/api'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const API_PREFIX = '/api/v1'

export class ApiRequestError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, payload: Partial<ApiError>) {
    super(payload.message ?? `Request failed with status ${status}`)
    this.name = 'ApiRequestError'
    this.status = status
    this.code = payload.code ?? 'unknown_error'
    this.details = payload.details ?? {}
  }

  /** True when re-authenticating is the fix. */
  get isAuthError(): boolean {
    return this.status === 401
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/**
 * Called whenever the API rejects a request as unauthenticated.
 *
 * Registered by AuthProvider. Lives here because a 401 can come back from any
 * query at any time — a refresh token that expired while a laptop was shut, a
 * revoked session, an account deactivated by an admin — and every one of those
 * should end the session rather than leaving the UI showing stale data it can
 * no longer refresh.
 */
type UnauthorizedHandler = () => void

let onUnauthorized: UnauthorizedHandler | null = null

export function setUnauthorizedHandler(handler: UnauthorizedHandler | null) {
  onUnauthorized = handler
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null>
  signal?: AbortSignal
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(
    `${API_PREFIX}${path}`,
    BASE_URL || window.location.origin,
  )
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value))
    }
  }
  return url.toString()
}

/**
 * Long enough for a sleeping free-tier backend to cold start (~50s), short
 * enough that a genuinely dead server does not hang the UI forever.
 */
const REQUEST_TIMEOUT_MS = 70_000

export async function apiFetch<T>(
  path: string,
  { method = 'GET', body, query, signal }: RequestOptions = {},
): Promise<T> {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS)
  const response = await fetch(buildUrl(path, query), {
    method,
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    headers: {
      'Content-Type': 'application/json',
      ...(await authHeader()),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })

  if (response.status === 204) {
    return undefined as T
  }

  const text = await response.text()
  const payload: unknown = text ? JSON.parse(text) : {}

  if (!response.ok) {
    const error = new ApiRequestError(response.status, payload as Partial<ApiError>)
    if (error.isAuthError) {
      onUnauthorized?.()
    }
    throw error
  }

  return payload as T
}

export const api = {
  get: <T>(path: string, query?: RequestOptions['query']) =>
    apiFetch<T>(path, { query }),
  post: <T>(path: string, body?: unknown, query?: RequestOptions['query']) =>
    apiFetch<T>(path, { method: 'POST', body, query }),
  patch: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: 'PATCH', body }),
  delete: <T>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
}
