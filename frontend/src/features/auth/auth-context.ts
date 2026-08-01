/**
 * The auth context object, kept apart from the provider component so that
 * editing the provider does not invalidate fast refresh for every consumer.
 */

import { createContext } from 'react'
import type { Session } from '@supabase/supabase-js'

import type { CurrentUser } from '@/types/api'

export interface AuthContextValue {
  session: Session | null
  user: CurrentUser | null
  status: 'loading' | 'authenticated' | 'anonymous'
  error: string | null
  signInWithGoogle: () => Promise<void>
  sendEmailOtp: (email: string) => Promise<void>
  verifyEmailOtp: (email: string, token: string) => Promise<void>
  signOut: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
