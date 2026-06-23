import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'
import React from 'react'
import { FollowPersonPage } from './FollowPersonPage'
import { useLiveStore } from './store/liveStore'
import type { PersonLocation } from './types'
import * as client from '@/shared/api/client'

vi.mock('@/shared/api/client', () => ({ api: { get: vi.fn(), patch: vi.fn() } }))

vi.mock('./components/FocusedCamera', () => ({
  FocusedCamera: vi.fn(({ cameraId }: { cameraId: number | null }) => (
    <div data-testid="focused-camera" data-camera-id={cameraId} />
  )),
}))

vi.mock('./components/AlertSidebar', () => ({
  AlertSidebar: vi.fn(() => <div data-testid="alert-sidebar" />),
}))

vi.mock('./components/TopBar', () => ({
  TopBar: vi.fn(() => <div data-testid="top-bar" />),
}))

vi.mock('./components/PersonDot', () => ({
  PersonDot: vi.fn(() => <div data-testid="person-dot" />),
}))

const mockApi = vi.mocked(client.api)
const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
  mockApi.get.mockResolvedValue([])
})

function renderAtRoute(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={[path]}>
        <QueryClientProvider client={qc}>
          <Routes>
            <Route path="/live/follow/:trackId" element={<FollowPersonPage />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>
    </HelmetProvider>,
  )
}

function addTrackedPerson(gid: string, cameraId: number) {
  const loc: PersonLocation = {
    global_track_id: gid, person_id: null, camera_id: cameraId,
    bbox: [0,0,0.5,0.5], floor_x: 0.3, floor_y: 0.4, ts: '2026-06-24T10:00:00Z',
  }
  useLiveStore.getState().applyLocations([loc])
}

describe('FollowPersonPage', () => {
  it('registers the trackId in liveStore on mount', () => {
    renderAtRoute('/live/follow/gid-42')
    expect(useLiveStore.getState().followedTrackId).toBe('gid-42')
  })

  it('shows the trackId in the timeline strip', () => {
    renderAtRoute('/live/follow/gid-42')
    expect(screen.getByText('gid-42')).toBeInTheDocument()
  })

  it('auto-switches focused camera to the camera holding the track', () => {
    addTrackedPerson('gid-5', 3)
    renderAtRoute('/live/follow/gid-5')
    expect(useLiveStore.getState().focusedCameraId).toBe(3)
  })

  it('shows camera ID in timeline strip when tracked', () => {
    addTrackedPerson('gid-5', 3)
    renderAtRoute('/live/follow/gid-5')
    expect(screen.getByText('Camera #3')).toBeInTheDocument()
  })

  it('clears followedTrackId on unmount', () => {
    const { unmount } = renderAtRoute('/live/follow/gid-42')
    expect(useLiveStore.getState().followedTrackId).toBe('gid-42')
    unmount()
    expect(useLiveStore.getState().followedTrackId).toBeNull()
  })

  it('renders alert sidebar', () => {
    renderAtRoute('/live/follow/gid-1')
    expect(screen.getByTestId('alert-sidebar')).toBeInTheDocument()
  })
})
