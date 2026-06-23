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

vi.mock('./components/FocusedCamera', () => ({
  FocusedCamera: vi.fn(({ cameraId }: { cameraId: number | null }) => (
    <div data-testid="focused-camera" data-camera-id={cameraId} />
  )),
}))

vi.mock('./components/CameraGrid', () => ({
  CameraGrid: vi.fn(({ cameras, focusedCameraId, onCameraSelect }: {
    cameras: CameraState[]
    focusedCameraId: number | null
    onCameraSelect: (id: number) => void
  }) => (
    <div data-testid="camera-grid" data-count={cameras.length} data-focused={focusedCameraId}>
      {cameras.map((c) => (
        <button key={c.camera_id} onClick={() => onCameraSelect(c.camera_id)}>
          {c.name}
        </button>
      ))}
    </div>
  )),
}))

vi.mock('./components/AlertSidebar', () => ({
  AlertSidebar: vi.fn(() => <div data-testid="alert-sidebar" />),
}))

vi.mock('./components/TopBar', () => ({
  TopBar: vi.fn(() => <div data-testid="top-bar" />),
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
    expect(screen.getByLabelText('Camera grid')).toBeInTheDocument()
    expect(screen.getByLabelText('Alert sidebar')).toBeInTheDocument()
    expect(screen.getByTestId('focused-camera')).toBeInTheDocument()
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

  it('passes cameras and focusedCameraId to CameraGrid', () => {
    const cameras = [makeCamera(1), makeCamera(2)]
    useLiveStore.setState({ cameras, focusedCameraId: 1 })
    render(<LivePage />, { wrapper: Wrapper })
    const grid = screen.getByTestId('camera-grid')
    expect(grid).toHaveAttribute('data-count', '2')
    expect(grid).toHaveAttribute('data-focused', '1')
  })
})
