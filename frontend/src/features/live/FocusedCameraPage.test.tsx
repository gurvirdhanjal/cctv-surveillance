import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'
import React from 'react'
import { FocusedCameraPage } from './FocusedCameraPage'
import { useLiveStore } from './store/liveStore'
import * as client from '@/shared/api/client'

vi.mock('@/shared/api/client', () => ({ api: { get: vi.fn(), patch: vi.fn() } }))
vi.mock('./LivePage', () => ({ LivePage: vi.fn(() => <div data-testid="live-page" />) }))

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
            <Route path="/live/cameras/:cameraId" element={<FocusedCameraPage />} />
          </Routes>
        </QueryClientProvider>
      </MemoryRouter>
    </HelmetProvider>,
  )
}

describe('FocusedCameraPage', () => {
  it('sets focusedCameraId in liveStore from URL param', () => {
    renderAtRoute('/live/cameras/7')
    expect(useLiveStore.getState().focusedCameraId).toBe(7)
  })

  it('renders LivePage', () => {
    const { getByTestId } = renderAtRoute('/live/cameras/3')
    expect(getByTestId('live-page')).toBeInTheDocument()
  })

  it('ignores non-numeric cameraId param', () => {
    renderAtRoute('/live/cameras/abc')
    expect(useLiveStore.getState().focusedCameraId).toBeNull()
  })
})
