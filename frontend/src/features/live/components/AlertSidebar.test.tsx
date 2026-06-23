import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { AlertSidebar } from './AlertSidebar'
import { useLiveStore } from '../store/liveStore'
import type { LiveAlert } from '../types'
import * as client from '@/shared/api/client'

vi.mock('@/shared/api/client', () => ({
  api: { get: vi.fn(), patch: vi.fn() },
}))

const mockApi = vi.mocked(client.api)

const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
  mockApi.get.mockResolvedValue([])
  mockApi.patch.mockResolvedValue({})
})

function Wrapper({ children }: React.PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return React.createElement(QueryClientProvider, { client: qc }, children)
}

function makeAlert(id: number, overrides: Partial<LiveAlert> = {}): LiveAlert {
  return {
    alert_id: id,
    alert_type: 'INTRUSION',
    severity: 'HIGH',
    state: 'OPEN',
    camera_id: 1,
    zone_id: null,
    person_id: null,
    triggered_at: new Date(Date.now() - id * 60_000).toISOString(),
    acknowledged_at: null,
    resolved_at: null,
    suppressed_by_window_id: null,
    dedup_key: null,
    global_track_id: null,
    snapshot_url: null,
    ...overrides,
  }
}

describe('AlertSidebar', () => {
  it('shows "No active alerts" when empty', () => {
    render(<AlertSidebar />, { wrapper: Wrapper })
    expect(screen.getByText('No active alerts')).toBeInTheDocument()
  })

  it('renders alert cards from liveStore', () => {
    useLiveStore.setState({ alerts: [makeAlert(1), makeAlert(2)] })
    render(<AlertSidebar />, { wrapper: Wrapper })
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('sorts CRITICAL before HIGH', () => {
    useLiveStore.setState({
      alerts: [
        makeAlert(1, { severity: 'HIGH' }),
        makeAlert(2, { severity: 'CRITICAL' }),
      ],
    })
    render(<AlertSidebar />, { wrapper: Wrapper })
    const items = screen.getAllByRole('listitem')
    expect(items[0].textContent).toContain('CRITICAL')
    expect(items[1].textContent).toContain('HIGH')
  })

  it('groups alerts with same global_track_id and shows +N similar', () => {
    useLiveStore.setState({
      alerts: [
        makeAlert(1, { global_track_id: 'gid-x' }),
        makeAlert(2, { global_track_id: 'gid-x' }),
        makeAlert(3, { global_track_id: 'gid-x' }),
      ],
    })
    render(<AlertSidebar />, { wrapper: Wrapper })
    expect(screen.getByText('+2 similar')).toBeInTheDocument()
    // Only 1 group item
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
  })

  it('filters by severity when dropdown changed', () => {
    useLiveStore.setState({
      alerts: [makeAlert(1, { severity: 'HIGH' }), makeAlert(2, { severity: 'CRITICAL' })],
    })
    render(<AlertSidebar />, { wrapper: Wrapper })
    fireEvent.change(screen.getByLabelText('Filter by severity'), {
      target: { value: 'CRITICAL' },
    })
    expect(screen.getAllByRole('listitem')).toHaveLength(1)
    expect(screen.getByRole('listitem').textContent).toContain('CRITICAL')
  })

  it('shows degraded banner when store is degraded', () => {
    useLiveStore.setState({ degraded: { connection: 'lost' } })
    render(<AlertSidebar />, { wrapper: Wrapper })
    expect(screen.getByText(/Alerts paused — system degraded/)).toBeInTheDocument()
  })
})
