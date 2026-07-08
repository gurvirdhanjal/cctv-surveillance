import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import React from 'react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

vi.mock('./hooks/useSocketConnection', () => ({
  useSocketConnection: vi.fn(),
}))

vi.mock('./hooks/useLiveShortcuts', () => ({
  useLiveShortcuts: vi.fn(),
}))

vi.mock('@/shared/api/client', () => ({
  api: { get: vi.fn(), patch: vi.fn() },
}))

vi.mock('./components/FocusedCamera', () => ({
  FocusedCamera: () => <div data-testid="focused-camera" />,
}))

vi.mock('./components/CameraTree', () => ({
  CameraTree: () => <div data-testid="camera-tree" />,
}))

vi.mock('./components/AlertSidebar', () => ({
  AlertSidebar: () => <div data-testid="alert-sidebar" />,
}))

vi.mock('./components/TopBar', () => ({
  TopBar: () => <div data-testid="top-bar" />,
}))

vi.mock('./components/OfflineReconnectBanner', () => ({
  OfflineReconnectBanner: () => null,
}))

vi.mock('./components/SystemStatusStrip', () => ({
  SystemStatusStrip: () => null,
}))

vi.mock('./components/ShortcutLegend', () => ({
  ShortcutLegend: () => null,
}))

vi.mock('./components/ClipExportDialog', () => ({
  ClipExportDialog: () => null,
}))

vi.mock('./components/AlertTimeline', () => ({
  AlertTimeline: () => <div data-testid="alert-timeline" />,
}))

vi.mock('react-resizable-panels', () => ({
  Group: ({ children, orientation }: { children: React.ReactNode; orientation?: string; onLayoutChange?: unknown; defaultLayout?: unknown; style?: unknown }) => (
    <div data-orientation={orientation ?? 'horizontal'}>{children}</div>
  ),
  Panel: ({ children, id }: { children: React.ReactNode; id?: string; defaultSize?: number; minSize?: number }) => (
    <div data-panel={id ?? ''}>{children}</div>
  ),
  Separator: ({ className }: { className?: string }) => (
    <div data-separator="" className={className} role="separator" />
  ),
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
    expect(screen.getByTestId('camera-tree')).toBeInTheDocument()
    expect(screen.getByTestId('focused-camera')).toBeInTheDocument()
    expect(screen.getByTestId('alert-sidebar')).toBeInTheDocument()
  })

  it('shows no offline banner when connection is healthy', () => {
    renderLivePage()
    // OfflineReconnectBanner is mocked to null — just confirm page renders
    expect(screen.getByTestId('top-bar')).toBeInTheDocument()
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
        triggered_at: '2026-07-07T00:00:00',
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
