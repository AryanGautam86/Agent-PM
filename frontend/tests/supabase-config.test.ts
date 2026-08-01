/**
 * Environment handling for the Supabase client.
 *
 * This module runs at import time, so anything it throws takes the whole app
 * down before React mounts — the user sees a blank page with no error in the
 * UI. That failure mode is why these cases are pinned.
 *
 * The specific trap: an unset variable in a `.env` file arrives as an empty
 * string, not `undefined`, so `??` does not fall back and `createClient('')`
 * throws.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('supabase client construction', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('constructs when the env vars are empty strings', async () => {
    vi.stubEnv('VITE_SUPABASE_URL', '')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', '')

    const module = await import('@/lib/supabase')

    expect(module.supabase).toBeDefined()
    expect(module.isSupabaseConfigured).toBe(false)
  })

  it('constructs when the env vars are whitespace only', async () => {
    vi.stubEnv('VITE_SUPABASE_URL', '   ')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', '  ')

    const module = await import('@/lib/supabase')

    expect(module.supabase).toBeDefined()
    expect(module.isSupabaseConfigured).toBe(false)
  })

  it('reports configured when both values are present', async () => {
    vi.stubEnv('VITE_SUPABASE_URL', 'https://abcdefgh.supabase.co')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', 'anon-key-value')

    const module = await import('@/lib/supabase')

    expect(module.isSupabaseConfigured).toBe(true)
  })

  it('is not configured when only one of the two is set', async () => {
    vi.stubEnv('VITE_SUPABASE_URL', 'https://abcdefgh.supabase.co')
    vi.stubEnv('VITE_SUPABASE_ANON_KEY', '')

    const module = await import('@/lib/supabase')

    expect(module.isSupabaseConfigured).toBe(false)
  })
})
