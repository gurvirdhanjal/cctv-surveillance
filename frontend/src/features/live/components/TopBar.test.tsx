import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { TopBar } from './TopBar'
import { useLiveStore } from '../store/liveStore'
import { useCommandPaletteStore } from '@/stores/commandPaletteStore'
import type { LiveAlert } from '../types'

vi.mock('@/shared/api/client', () => ({
  api: { get: vi.fn(), patch: vi.fn() },
}))

const initialLive = useLiveStore.getState()
const initialPalette = useCommandPaletteStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialLive, true)
  useCommandPaletteStore.setState(initialPalette, true)
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

  it('clicking search trigger opens CommandPalette store', () => {
    render(<TopBar />, { wrapper: Wrapper })
    fireEvent.click(screen.getByLabelText('Search persons'))
    expect(useCommandPaletteStore.getState().open).toBe(true)
  })

  it('shows active alert count badge when there are open alerts', () => {
    useLiveStore.setState({ alerts: [makeAlert('OPEN'), makeAlert('OPEN')] })
    render(<TopBar />, { wrapper: Wrapper })
    expect(screen.getByLabelText('2 active alerts')).toBeInTheDocument()
  })

  it('does not show alerts badge when no open alerts', () => {
    useLiveStore.setState({ alerts: [makeAlert('RESOLVED')] })
    render(<TopBar />, { wrapper: Wrapper })
    expect(screen.queryByLabelText(/active alerts/)).toBeNull()
  })

  it('GPU bar width reflects gpuPct', () => {
    useLiveStore.setState({ gpuPct: 75 })
    render(<TopBar />, { wrapper: Wrapper })
    const bar = screen.getByRole('progressbar', { name: 'GPU 75%' })
    expect(bar).toBeInTheDocument()
    expect(bar).toHaveAttribute('aria-valuenow', '75')
  })

  it('GPU label shows percentage', () => {
    useLiveStore.setState({ gpuPct: 42 })
    render(<TopBar />, { wrapper: Wrapper })
    expect(screen.getByText('42%')).toBeInTheDocument()
  })

  it('head count label shows total', () => {
    useLiveStore.setState({ headCount: { total: 17, byZone: {} } })
    render(<TopBar />, { wrapper: Wrapper })
    expect(screen.getByLabelText('17 people on site')).toBeInTheDocument()
  })
})
