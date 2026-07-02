import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

// Mock socket connection so it doesn't try to connect in tests
vi.mock('./hooks/useSocketConnection', () => ({
  useSocketConnection: vi.fn(),
}))

vi.mock('@/shared/api/client', () => ({
  api: { get: vi.fn(), patch: vi.fn() },
}))

// Minimal mocks for heavy components
vi.mock('./components/FocusedCamera', () => ({
  FocusedCamera: () => <div data-testid="focused-camera" />,
}))
vi.mock('./components/CameraGrid', () => ({
  CameraGrid: () => <div data-testid="camera-grid" />,
}))
vi.mock('./components/AlertSidebar', () => ({
  AlertSidebar: () => <div data-testid="alert-sidebar" />,
}))
vi.mock('./components/TopBar', () => ({
  TopBar: () => <div data-testid="top-bar" />,
}))

import { api } from '@/shared/api/client'
import { useLiveStore } from './store/liveStore'
import { LivePage } from './LivePage'

function renderLivePage() {
  return render(
    <HelmetProvider>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <LivePage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

describe('LivePage integration', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockResolvedValue([])
    useLiveStore.setState({
      cameras: [],
      alerts: [],
      degraded: null,
      focusedCameraId: null,
      followedTrackId: null,
      trackedPersons: new Map(),
      headCount: { total: 0, byZone: {} },
    })
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('renders all three layout panels', () => {
    renderLivePage()
    expect(screen.getByTestId('camera-grid')).toBeInTheDocument()
    expect(screen.getByTestId('focused-camera')).toBeInTheDocument()
    expect(screen.getByTestId('alert-sidebar')).toBeInTheDocument()
  })

  it('shows no degraded banner when connection is healthy', () => {
    renderLivePage()
    expect(screen.queryByRole('status', { name: 'Connection degraded' })).not.toBeInTheDocument()
  })

  it('shows DegradedBanner when store is degraded', () => {
    useLiveStore.setState({ degraded: { connection: 'lost' } })
    renderLivePage()
    expect(screen.getByRole('status', { name: 'Connection degraded' })).toBeInTheDocument()
    expect(screen.getByText(/Reconnecting/)).toBeInTheDocument()
  })

  it('removes DegradedBanner when store recovers', () => {
    useLiveStore.setState({ degraded: { connection: 'lost' } })
    renderLivePage()
    expect(screen.getByRole('status', { name: 'Connection degraded' })).toBeInTheDocument()

    act(() => {
      useLiveStore.setState({ degraded: null })
    })
    expect(screen.queryByRole('status', { name: 'Connection degraded' })).not.toBeInTheDocument()
  })

  it('applies an alert_fired event via store to update alert list', () => {
    renderLivePage()
    act(() => {
      useLiveStore.getState().applyAlertFired({
        alert_id: 1,
        alert_type: 'INTRUSION',
        severity: 'HIGH',
        state: 'OPEN',
        camera_id: 1,
        zone_id: null,
        person_id: null,
        triggered_at: '2026-07-02T00:00:00',
        acknowledged_at: null,
        resolved_at: null,
        suppressed_by_window_id: null,
        dedup_key: null,
        global_track_id: null,
        snapshot_url: null,
      })
    })
    expect(useLiveStore.getState().alerts).toHaveLength(1)
  })
})
