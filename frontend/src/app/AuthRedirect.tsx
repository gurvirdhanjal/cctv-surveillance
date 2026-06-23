import { useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

export const UNAUTHORIZED_EVENT = 'vms:unauthorized'

/**
 * Listens for the custom `vms:unauthorized` event (fired by the API client on 401)
 * and redirects to /login, preserving the current path as ?next=.
 * Also hydrates the auth store from localStorage on mount.
 */
export function AuthRedirect() {
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    useAuthStore.getState().hydrate()
  }, [])

  useEffect(() => {
    function handleUnauthorized() {
      // Clear stale token
      useAuthStore.getState().logout()
      const next = encodeURIComponent(location.pathname)
      navigate(`/login?next=${next}`, { replace: true })
    }

    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized)
  }, [navigate, location.pathname])

  return null
}
