import { useAuthStore } from '@/stores/authStore'

/** Convenience hook — returns the current user and auth actions. */
export function useAuth() {
  const user = useAuthStore((s) => s.user)
  const token = useAuthStore((s) => s.token)
  const isLoading = useAuthStore((s) => s.isLoading)
  const error = useAuthStore((s) => s.error)
  const login = useAuthStore((s) => s.login)
  const logout = useAuthStore((s) => s.logout)

  return {
    user,
    token,
    isAuthenticated: token !== null && user !== null,
    isLoading,
    error,
    login,
    logout,
  }
}
