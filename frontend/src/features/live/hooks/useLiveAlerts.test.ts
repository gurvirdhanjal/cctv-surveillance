import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { useLiveAlerts } from './useLiveAlerts'
import { useLiveStore } from '../store/liveStore'
import * as client from '@/shared/api/client'
import type { AlertResponse } from '@/shared/api/types'

vi.mock('@/shared/api/client', () => ({
  api: {
    get: vi.fn(),
    patch: vi.fn(),
  },
}))

const mockApi = vi.mocked(client.api)

const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
  vi.restoreAllMocks()
})

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: PropsWithChildren) {
    return React.createElement(QueryClientProvider, { client }, children)
  }
}

const mockAlerts: AlertResponse[] = [
  {
    alert_id: 1,
    alert_type: 'INTRUSION',
    severity: 'HIGH',
    state: 'OPEN',
    camera_id: 1,
    zone_id: null,
    person_id: null,
    triggered_at: '2026-06-24T10:00:00Z',
    acknowledged_at: null,
    resolved_at: null,
    suppressed_by_window_id: null,
    dedup_key: null,
  },
]

describe('useLiveAlerts', () => {
  it('seeds liveStore.alerts from GET /api/alerts?state=OPEN', async () => {
    mockApi.get.mockResolvedValueOnce(mockAlerts)

    renderHook(() => useLiveAlerts(), { wrapper: makeWrapper() })

    await waitFor(() => {
      expect(useLiveStore.getState().alerts).toHaveLength(1)
    })
    expect(useLiveStore.getState().alerts[0].alert_id).toBe(1)
    expect(useLiveStore.getState().alerts[0].global_track_id).toBeNull()
  })

  it('acknowledge updates alert state optimistically then calls PATCH', async () => {
    mockApi.get.mockResolvedValueOnce(mockAlerts)
    mockApi.patch.mockResolvedValueOnce({})

    const { result } = renderHook(() => useLiveAlerts(), { wrapper: makeWrapper() })

    await waitFor(() => {
      expect(useLiveStore.getState().alerts).toHaveLength(1)
    })

    await result.current.acknowledge(1)

    expect(useLiveStore.getState().alerts[0].state).toBe('ACKNOWLEDGED')
    expect(mockApi.patch).toHaveBeenCalledWith('/api/alerts/1', { state: 'ACKNOWLEDGED' })
  })

  it('acknowledge rolls back to OPEN on API error', async () => {
    mockApi.get.mockResolvedValueOnce(mockAlerts)
    mockApi.patch.mockRejectedValueOnce(new Error('500'))

    const { result } = renderHook(() => useLiveAlerts(), { wrapper: makeWrapper() })

    await waitFor(() => {
      expect(useLiveStore.getState().alerts).toHaveLength(1)
    })

    await result.current.acknowledge(1)
    expect(useLiveStore.getState().alerts[0].state).toBe('OPEN')
  })

  it('resolve updates alert state optimistically then calls PATCH', async () => {
    mockApi.get.mockResolvedValueOnce(mockAlerts)
    mockApi.patch.mockResolvedValueOnce({})

    const { result } = renderHook(() => useLiveAlerts(), { wrapper: makeWrapper() })

    await waitFor(() => {
      expect(useLiveStore.getState().alerts).toHaveLength(1)
    })

    await result.current.resolve(1)

    expect(useLiveStore.getState().alerts[0].state).toBe('RESOLVED')
    expect(mockApi.patch).toHaveBeenCalledWith('/api/alerts/1', { state: 'RESOLVED' })
  })
})
