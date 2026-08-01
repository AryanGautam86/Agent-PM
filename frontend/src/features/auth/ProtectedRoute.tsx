import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { Spinner } from '@/components/ui/Spinner'
import { useAuth } from '@/features/auth/useAuth'

export function ProtectedRoute() {
  const { status, error } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div className="center-screen">
        <Spinner label="Checking your session" />
      </div>
    )
  }

  if (status === 'anonymous') {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname, reason: error }}
      />
    )
  }

  return <Outlet />
}
