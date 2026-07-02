import { create } from 'zustand'
import { api } from '@/shared/api/client'
import type { JwtPayload, TokenResponse } from '@/shared/api/types'

const STORAGE_KEY = 'vms-auth'

export type UserRole = 'guard' | 'manager' | 'admin'

export interface AuthUser {
  userId: string
  role: UserRole
  exp: number
}

interface AuthState {
  token: string | null
  user: AuthUser | null
  /** True while login request is in flight. */
  isLoading: boolean
  /** Login error message, if last attempt failed. */
  error: string | null
}

interface AuthActions {
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  /** Called on app mount to rehydrate from localStorage. */
  hydrate: () => void
}

function decodeJwt(token: string): JwtPayload | null {
  try {
    const [, payload] = token.split('.')
    return JSON.parse(atob(payload)) as JwtPayload
  } catch {
    return null
  }
}

function isExpired(payload: JwtPayload): boolean {
  return payload.exp * 1000 < Date.now()
}

export const useAuthStore = create<AuthState & AuthActions>((set) => ({
  token: null,
  user: null,
  isLoading: false,
  error: null,

  hydrate: () => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const { token } = JSON.parse(raw) as { token: string }
      const payload = decodeJwt(token)
      if (!payload || isExpired(payload)) {
        localStorage.removeItem(STORAGE_KEY)
        return
      }
      set({
        token,
        user: { userId: payload.sub, role: payload.role, exp: payload.exp },
      })
    } catch {
      localStorage.removeItem(STORAGE_KEY)
    }
  },

  login: async (username, password) => {
    set({ isLoading: true, error: null })
    try {
      const res = await api.post<TokenResponse>('/api/auth/token', { username, password }, {
        skipAuth: true,
      })
      const payload = decodeJwt(res.access_token)
      if (!payload) throw new Error('Invalid token received')
      const user: AuthUser = { userId: payload.sub, role: payload.role, exp: payload.exp }
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: res.access_token }))
      set({ token: res.access_token, user, isLoading: false, error: null })
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Invalid username or password.'
      set({ isLoading: false, error: message })
      throw err
    }
  },

  logout: () => {
    localStorage.removeItem(STORAGE_KEY)
    set({ token: null, user: null, error: null })
  },
}))
