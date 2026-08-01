import { createBrowserRouter, type RouteObject } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { ActionItemsPage } from '@/features/action_items/ActionItemsPage'
import { AuthCallbackPage } from '@/features/auth/AuthCallbackPage'
import { LoginPage } from '@/features/auth/LoginPage'
import { ProtectedRoute } from '@/features/auth/ProtectedRoute'
import { ReportsPage } from '@/features/reports/ReportsPage'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { StandupsPage } from '@/features/standups/StandupsPage'
import { TeamPage } from '@/features/team/TeamPage'
import { NotFoundPage } from '@/pages/NotFoundPage'

/**
 * The route table, exported separately from the router itself so tests can
 * mount it with `createMemoryRouter`. A browser router needs real history and
 * constructs `Request` objects that jsdom cannot satisfy.
 */
export const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  { path: '/auth/callback', element: <AuthCallbackPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: 'standups', element: <StandupsPage /> },
          { path: 'action-items', element: <ActionItemsPage /> },
          { path: 'reports', element: <ReportsPage /> },
          { path: 'team', element: <TeamPage /> },
        ],
      },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
]

export const router = createBrowserRouter(routes)
