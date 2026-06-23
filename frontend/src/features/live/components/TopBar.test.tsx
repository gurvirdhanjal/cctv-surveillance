import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { TopBar } from './TopBar'
import { useLiveStore } from '../store/liveStore'
import * as client from '@/shared/api/client'
import type { LiveAlert } from '../types'

vi.mock('@/shared/api/client', () => ({
  api: { get: vi.fn(), patch: vi.fn() },
}))

// Mock HeadCountBanner to avoid store noise
vi.mock('./HeadCountBanner', () => ({
  HeadCountBanner: () => <span data-testid="head-count-banner" />,
}))

const mockApi = vi.mocked(client.api)

const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
  mockApi.get.mockResolvedValue([])
  vi.restoreAllMocks()
})

function Wrapper({ children }: React.PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  )
}

function makeAlert(state: string = 'OPEN'): LiveAlert {
  return {
    alert_id: 1, alert_type: 'INTRUSION', severity: 'HIGH',
    state: state as LiveAlert['state'],
    camera_id: 1, zone_id: null, person_id: null,
    triggered_at: new Date().toISOString(),
    acknowledged_at: null, resolved_at: null,
    suppressed_by_window_id: null, dedup_key: null,
    global_track_id: null, snapshot_url: null,
  }
}

describe('TopBar', () => {
  it('renders VMS logo link', () => {
    render(<TopBar />, { wrapper: Wrapper })
    expect(screen.getByLabelText('VMS — home')).toBeInTheDocument()
  })

  it('renders search trigger button', () => {
    render(<TopBar />, { wrapper: Wrapper })
    expect(screen.getByLabelText('Search persons')).toBeInTheDocument()
  })

  it('opens search dialog on button click', () => {
    render(<TopBar />, { wrapper: Wrapper })
    fireEvent.click(screen.getByLabelText('Search persons'))
    expect(screen.getByRole('dialog', { name: 'Person search' })).toBeInTheDocument()
  })

  it('opens search dialog on Ctrl+K', () => {
    render(<TopBar />, { wrapper: Wrapper })
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    expect(screen.getByRole('dialog', { name: 'Person search' })).toBeInTheDocument()
  })

  it('closes search dialog on Escape', () => {
    render(<TopBar />, { wrapper: Wrapper })
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true })
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('shows active alert count when there are open alerts', () => {
    useLiveStore.setState({ alerts: [makeAlert('OPEN'), makeAlert('OPEN')] })
    render(<TopBar />, { wrapper: Wrapper })
    expect(screen.getByLabelText('2 active alerts')).toBeInTheDocument()
  })

  it('does not show alerts badge when no open alerts', () => {
    useLiveStore.setState({ alerts: [makeAlert('RESOLVED')] })
    render(<TopBar />, { wrapper: Wrapper })
    expect(screen.queryByLabelText(/active alerts/)).toBeNull()
  })

  it('shows search results from /api/persons/search', async () => {
    mockApi.get.mockResolvedValueOnce([
      { person_id: 1, name: 'John Doe', employee_id: 'EMP-001', is_active: true },
    ])
    render(<TopBar />, { wrapper: Wrapper })
    fireEvent.click(screen.getByLabelText('Search persons'))
    fireEvent.change(screen.getByLabelText('Search persons', { selector: 'input' }), {
      target: { value: 'John' },
    })
    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeInTheDocument()
    })
  })
})
