import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { useAuthStore } from './authStore'
import { UnauthorizedError } from '@/shared/api/errors'

// A real JWT with role=guard, exp=9999999999 (far future)
const GUARD_TOKEN =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
  btoa(JSON.stringify({ sub: '7', role: 'guard', exp: 9_999_999_999 })).replace(/=/g, '') +
  '.sig'

const ADMIN_TOKEN =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
  btoa(JSON.stringify({ sub: '1', role: 'admin', exp: 9_999_999_999 })).replace(/=/g, '') +
  '.sig'

const EXPIRED_TOKEN =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
  btoa(JSON.stringify({ sub: '1', role: 'admin', exp: 1 })).replace(/=/g, '') +
  '.sig'

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({ token: null, user: null, isLoading: false, error: null })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('authStore — hydrate', () => {
  it('rehydrates user from localStorage on mount', () => {
    localStorage.setItem('vms-auth', JSON.stringify({ token: GUARD_TOKEN }))
    useAuthStore.getState().hydrate()
    const { user, token } = useAuthStore.getState()
    expect(token).toBe(GUARD_TOKEN)
    expect(user?.role).toBe('guard')
    expect(user?.userId).toBe('7')
  })

  it('clears expired token on hydrate', () => {
    localStorage.setItem('vms-auth', JSON.stringify({ token: EXPIRED_TOKEN }))
    useAuthStore.getState().hydrate()
    expect(useAuthStore.getState().token).toBeNull()
    expect(localStorage.getItem('vms-auth')).toBeNull()
  })

  it('does nothing when localStorage is empty', () => {
    useAuthStore.getState().hydrate()
    expect(useAuthStore.getState().user).toBeNull()
  })
})

describe('authStore — login', () => {
  it('stores token and decoded user on success', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ access_token: ADMIN_TOKEN, token_type: 'bearer' }),
    } as Response)

    await useAuthStore.getState().login('admin', 'secret')

    const { user, token } = useAuthStore.getState()
    expect(token).toBe(ADMIN_TOKEN)
    expect(user?.role).toBe('admin')
    expect(user?.userId).toBe('1')
    expect(localStorage.getItem('vms-auth')).toContain(ADMIN_TOKEN)
  })

  it('sets error and throws on 401', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: 'Incorrect credentials' }),
    } as Response)

    await expect(useAuthStore.getState().login('x', 'y')).rejects.toBeInstanceOf(UnauthorizedError)
    expect(useAuthStore.getState().error).toBeTruthy()
    expect(useAuthStore.getState().user).toBeNull()
  })

  it('sets isLoading=true during request, false after', async () => {
    let resolveLogin!: (v: unknown) => void
    globalThis.fetch = vi.fn().mockReturnValue(
      new Promise((res) => {
        resolveLogin = res
      }),
    )
    const loginPromise = useAuthStore.getState().login('u', 'p')
    expect(useAuthStore.getState().isLoading).toBe(true)
    resolveLogin({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ access_token: GUARD_TOKEN, token_type: 'bearer' }),
    })
    await loginPromise
    expect(useAuthStore.getState().isLoading).toBe(false)
  })
})

describe('authStore — logout', () => {
  it('clears token and user', () => {
    useAuthStore.setState({ token: GUARD_TOKEN, user: { userId: '7', role: 'guard', exp: 9999 } })
    useAuthStore.getState().logout()
    expect(useAuthStore.getState().token).toBeNull()
    expect(useAuthStore.getState().user).toBeNull()
    expect(localStorage.getItem('vms-auth')).toBeNull()
  })
})
