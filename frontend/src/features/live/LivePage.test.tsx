import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'
import React from 'react'
import { LivePage } from './LivePage'
import { useLiveStore } from './store/liveStore'
import type { CameraState } from './types'
import * as client from '@/shared/api/client'

vi.mock('@/shared/api/client', () => ({
  api: { get: vi.fn(), patch: vi.fn() },
}))

vi.mock('react-resizable-panels', () => ({
  Group: vi.fn(({ children, orientation }: React.PropsWithChildren<{ orientation?: string; onLayoutChange?: unknown; defaultLayout?: unknown; style?: unknown }>) => (
    <div data-orientation={orientation ?? 'horizontal'}>{children}</div>
  )),
  Panel: vi.fn(({ children, id }: React.PropsWithChildren<{ id?: string; defaultSize?: number; minSize?: number }>) => (
    <div data-panel={id ?? ''}>{children}</div>
  )),
  Separator: vi.fn(({ className }: { className?: string }) => (
    <div data-separator="" className={className} role="separator" />
  )),
}))

vi.mock('./components/FocusedCamera', () => ({
  FocusedCamera: vi.fn(({ cameraId }: { cameraId: number | null }) => (
    <div data-testid="focused-camera" data-camera-id={cameraId} />
  )),
}))

vi.mock('./components/CameraTree', () => ({
  CameraTree: vi.fn(() => <div data-testid="camera-tree" />),
}))

vi.mock('./components/AlertSidebar', () => ({
  AlertSidebar: vi.fn(() => <div data-testid="alert-sidebar" />),
}))

vi.mock('./components/TopBar', () => ({
  TopBar: vi.fn(() => <div data-testid="top-bar" />),
}))

vi.mock('./components/OfflineReconnectBanner', () => ({
  OfflineReconnectBanner: vi.fn(() => null),
}))

vi.mock('./components/SystemStatusStrip', () => ({
  SystemStatusStrip: vi.fn(() => <div data-testid="system-status-strip" />),
}))

vi.mock('./components/ShortcutLegend', () => ({
  ShortcutLegend: vi.fn(() => null),
}))

vi.mock('./components/ClipExportDialog', () => ({
  ClipExportDialog: vi.fn(() => null),
}))

vi.mock('./hooks/useLiveShortcuts', () => ({
  useLiveShortcuts: vi.fn(),
}))

vi.mock('./components/AlertTimeline', () => ({
  AlertTimeline: vi.fn(() => <div data-testid="alert-timeline" style={{ height: '120px' }} />),
}))

const mockApi = vi.mocked(client.api)
const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
  mockApi.get.mockResolvedValue([])
})

function Wrapper({ children }: React.PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <HelmetProvider>
      <MemoryRouter>
        <QueryClientProvider client={qc}>{children}</QueryClientProvider>
      </MemoryRouter>
    </HelmetProvider>
  )
}

function makeCamera(id: number): CameraState {
  return {
    camera_id: id, name: `Cam ${id}`, capability_tier: 'FULL',
    status: 'online', is_active: true, snapshotUrl: null,
  }
}

describe('LivePage', () => {
  it('renders all three columns', () => {
    render(<LivePage />, { wrapper: Wrapper })
    expect(screen.getByRole('region', { name: 'Camera list' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Alerts' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Focused camera' })).toBeInTheDocument()
    expect(screen.getByTestId('top-bar')).toBeInTheDocument()
  })

  it('auto-selects first camera when no camera is focused', () => {
    useLiveStore.setState({ cameras: [makeCamera(1), makeCamera(2)], focusedCameraId: null })
    render(<LivePage />, { wrapper: Wrapper })
    expect(useLiveStore.getState().focusedCameraId).toBe(1)
  })

  it('does not override an existing focused camera', () => {
    useLiveStore.setState({ cameras: [makeCamera(1), makeCamera(2)], focusedCameraId: 2 })
    render(<LivePage />, { wrapper: Wrapper })
    expect(useLiveStore.getState().focusedCameraId).toBe(2)
  })

  it('renders CameraTree in left column', () => {
    render(<LivePage />, { wrapper: Wrapper })
    expect(screen.getByTestId('camera-tree')).toBeInTheDocument()
  })

  it('renders PanelGroup with horizontal orientation', () => {
    const { container } = render(<LivePage />, { wrapper: Wrapper })
    const panelGroup = container.querySelector('[data-orientation="horizontal"]')
    expect(panelGroup).not.toBeNull()
  })

  it('renders three panels', () => {
    const { container } = render(<LivePage />, { wrapper: Wrapper })
    const panels = container.querySelectorAll('[data-panel]')
    expect(panels.length).toBe(3)
  })

  it('renders two resize separators', () => {
    const { container } = render(<LivePage />, { wrapper: Wrapper })
    const handles = container.querySelectorAll('[data-separator]')
    expect(handles.length).toBe(2)
  })

  it('renders alert timeline row', () => {
    render(<LivePage />, { wrapper: Wrapper })
    expect(screen.getByTestId('alert-timeline')).toBeInTheDocument()
  })
})
