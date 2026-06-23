import { type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import type { UserRole } from '@/stores/authStore'

interface RoleGuardProps {
  /** Roles allowed to access the wrapped route. */
  allow: UserRole[]
  children: ReactNode
}

/**
 * Redirects unauthenticated users to /login and unauthorised roles to /403.
 * Passes the current path as ?next= so login can restore the original destination.
 */
export function RoleGuard({ allow, children }: RoleGuardProps) {
  const { isAuthenticated, user } = useAuth()
  const location = useLocation()

  if (!isAuthenticated) {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />
  }

  if (user && !allow.includes(user.role)) {
    return <Navigate to="/403" replace />
  }

  return <>{children}</>
}
