import { mapHttpError, UnauthorizedError } from './errors'

/** Fired globally when any request receives a 401, allowing the app to redirect. */
const UNAUTHORIZED_EVENT = 'vms:unauthorized'

const BASE = ''

/** Retrieve the JWT stored by authStore (avoids a circular import). */
function getToken(): string | null {
  try {
    const raw = localStorage.getItem('vms-auth')
    if (!raw) return null
    return (JSON.parse(raw) as { token?: string }).token ?? null
  } catch {
    return null
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  /** Skip the Authorization header (e.g. login endpoint). */
  skipAuth?: boolean
}

/** Core fetch wrapper. Throws a typed ApiError on any non-2xx status. */
export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { body, skipAuth, ...init } = opts

  const headers = new Headers(init.headers)
  if (body !== undefined) headers.set('Content-Type', 'application/json')

  if (!skipAuth) {
    const token = getToken()
    if (token) headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (!response.ok) {
    let errorBody: unknown
    try {
      errorBody = await response.json()
    } catch {
      errorBody = undefined
    }
    const mapped = mapHttpError(response.status, errorBody)
    if (mapped instanceof UnauthorizedError) {
      window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
    }
    throw mapped
  }

  // 204 No Content — return undefined cast to T
  if (response.status === 204) return undefined as T

  return response.json() as Promise<T>
}

export const api = {
  get: <T>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'GET' }),

  post: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'POST', body }),

  patch: <T>(path: string, body?: unknown, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'PATCH', body }),

  delete: <T = void>(path: string, opts?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...opts, method: 'DELETE' }),
}
