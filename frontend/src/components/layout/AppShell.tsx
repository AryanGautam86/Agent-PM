import { NavLink, Outlet } from 'react-router-dom'

import { Spinner } from '@/components/ui/Spinner'
import { useAuth } from '@/features/auth/useAuth'
import { useSelectedEngagement } from '@/hooks/useEngagements'

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/standups', label: 'Standups', end: false },
  { to: '/action-items', label: 'Tasks', end: false },
  { to: '/reports', label: 'Reports', end: false },
  { to: '/team', label: 'Team', end: false },
]

export function AppShell() {
  const { user, signOut } = useAuth()
  const { engagements, engagement, isLoading, select } = useSelectedEngagement()

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <span className="auth-mark" aria-hidden="true">
            PM
          </span>
          <div>
            <strong>Agent-PM</strong>
            <p className="muted">Delivery Steward</p>
          </div>
        </div>

        <label className="sidebar-select">
          <span className="muted">Engagement</span>
          <select
            value={engagement?.id ?? ''}
            onChange={(event) => select(event.target.value)}
            disabled={isLoading || engagements.length === 0}
          >
            {engagements.length === 0 && <option value="">No engagements</option>}
            {engagements.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
              </option>
            ))}
          </select>
        </label>

        <nav className="sidebar-nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `nav-link ${isActive ? 'nav-link-active' : ''}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          {user && (
            <div className="user-chip">
              {user.avatar_url ? (
                <img src={user.avatar_url} alt="" width={28} height={28} />
              ) : (
                <span className="avatar-fallback" aria-hidden="true">
                  {(user.full_name ?? user.email).charAt(0).toUpperCase()}
                </span>
              )}
              <div className="user-chip-text">
                <strong>{user.full_name ?? user.email}</strong>
                <span className="muted">{user.role.replace(/_/g, ' ')}</span>
              </div>
            </div>
          )}
          <button className="link" onClick={() => void signOut()}>
            Sign out
          </button>
        </div>
      </aside>

      <main className="main">
        {isLoading ? <Spinner label="Loading your pods" /> : <Outlet />}
      </main>
    </div>
  )
}
