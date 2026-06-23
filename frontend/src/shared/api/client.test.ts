import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  ApiError,
  UnauthorizedError,
  ForbiddenError,
  NotFoundError,
  ValidationError,
  ServerError,
  mapHttpError,
} from './errors'

describe('mapHttpError', () => {
  it('maps 401 → UnauthorizedError', () => {
    expect(mapHttpError(401)).toBeInstanceOf(UnauthorizedError)
  })

  it('maps 403 → ForbiddenError', () => {
    expect(mapHttpError(403)).toBeInstanceOf(ForbiddenError)
  })

  it('maps 404 → NotFoundError', () => {
    expect(mapHttpError(404)).toBeInstanceOf(NotFoundError)
  })

  it('maps 422 → ValidationError', () => {
    expect(mapHttpError(422)).toBeInstanceOf(ValidationError)
  })

  it('maps 500 → ServerError', () => {
    expect(mapHttpError(500)).toBeInstanceOf(ServerError)
  })

  it('maps 503 → ServerError', () => {
    expect(mapHttpError(503)).toBeInstanceOf(ServerError)
  })

  it('all errors extend ApiError', () => {
    const codes = [401, 403, 404, 422, 500]
    for (const code of codes) {
      expect(mapHttpError(code)).toBeInstanceOf(ApiError)
    }
  })

  it('attaches status to error', () => {
    const err = mapHttpError(403, { detail: 'nope' })
    expect(err.status).toBe(403)
    expect((err.body as { detail: string }).detail).toBe('nope')
  })
})

describe('api client — fetch mocking', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  function mockFetch(status: number, body: unknown = null) {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
    } as Response)
  }

  it('returns parsed JSON on 2xx', async () => {
    mockFetch(200, { id: 1 })
    const { api } = await import('./client')
    const result = await api.get<{ id: number }>('/api/test')
    expect(result).toEqual({ id: 1 })
  })

  it('throws UnauthorizedError on 401', async () => {
    mockFetch(401, { detail: 'Not authenticated' })
    const { api } = await import('./client')
    await expect(api.get('/api/test')).rejects.toBeInstanceOf(UnauthorizedError)
  })

  it('throws ForbiddenError on 403', async () => {
    mockFetch(403)
    const { api } = await import('./client')
    await expect(api.get('/api/test')).rejects.toBeInstanceOf(ForbiddenError)
  })

  it('throws NotFoundError on 404', async () => {
    mockFetch(404)
    const { api } = await import('./client')
    await expect(api.get('/api/test')).rejects.toBeInstanceOf(NotFoundError)
  })

  it('throws ValidationError on 422', async () => {
    mockFetch(422)
    const { api } = await import('./client')
    await expect(api.post('/api/test', {})).rejects.toBeInstanceOf(ValidationError)
  })

  it('throws ServerError on 500', async () => {
    mockFetch(500)
    const { api } = await import('./client')
    await expect(api.get('/api/test')).rejects.toBeInstanceOf(ServerError)
  })

  it('injects Authorization header when token in localStorage', async () => {
    localStorage.setItem('vms-auth', JSON.stringify({ token: 'my-jwt' }))
    mockFetch(200, {})
    const { api } = await import('./client')
    await api.get('/api/test')
    const fetchCall = vi.mocked(globalThis.fetch).mock.calls[0]
    const headers = fetchCall[1]?.headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer my-jwt')
  })

  it('skips Authorization when skipAuth=true', async () => {
    localStorage.setItem('vms-auth', JSON.stringify({ token: 'my-jwt' }))
    mockFetch(200, {})
    const { request } = await import('./client')
    await request('/api/auth/token', { method: 'POST', skipAuth: true, body: {} })
    const fetchCall = vi.mocked(globalThis.fetch).mock.calls[0]
    const headers = fetchCall[1]?.headers as Headers
    expect(headers.get('Authorization')).toBeNull()
  })
})
