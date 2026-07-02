import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

vi.mock('@/shared/api/client', () => ({ api: { get: vi.fn() } }))
vi.mock('./camera-tabs/HardwareTab', () => ({
  HardwareTab: () => <div data-testid="hardware-tab" />,
}))
vi.mock('./camera-tabs/OverridesTab', () => ({
  OverridesTab: () => <div data-testid="overrides-tab" />,
}))
vi.mock('./camera-tabs/HomographyCalibrator', () => ({
  HomographyCalibrator: () => <div data-testid="homography-calibrator" />,
}))

import { api } from '@/shared/api/client'
const { CameraDetailPage } = await import('./CameraDetailPage')

const CAMERA = {
  camera_id: 3,
  name: 'Assembly Line 1',
  rtsp_url: 'rtsp://cam/stream',
  is_active: true,
  capability_tier: 'FULL',
  shutter_type: 'rolling',
  profile_data: null,
  profiled_at: '2026-06-24T10:00:00Z',
  model_overrides: null,
  worker_group: null,
  recalibrate_required_at: null,
}

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage(camId = '3') {
  return render(
    <HelmetProvider>
      <QueryClientProvider client={makeClient()}>
        <MemoryRouter initialEntries={[`/admin/cameras/${camId}`]}>
          <Routes>
            <Route path="/admin/cameras/:cameraId" element={<CameraDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

describe('CameraDetailPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  it('renders camera name after load', async () => {
    vi.mocked(api.get).mockResolvedValue(CAMERA)
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Assembly Line 1' })).toBeInTheDocument()
  })

  it('renders 5 tabs', async () => {
    vi.mocked(api.get).mockResolvedValue(CAMERA)
    renderPage()
    await screen.findByRole('heading', { name: 'Assembly Line 1' })
    const tablist = screen.getByRole('tablist', { name: 'Camera configuration tabs' })
    expect(tablist).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Profile' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Hardware' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Overrides' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Topology' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Resolved Config' })).toBeInTheDocument()
  })

  it('Profile tab is selected by default', async () => {
    vi.mocked(api.get).mockResolvedValue(CAMERA)
    renderPage()
    await screen.findByRole('heading', { name: 'Assembly Line 1' })
    expect(screen.getByRole('tab', { name: 'Profile' })).toHaveAttribute('aria-selected', 'true')
  })

  it('switches to Hardware tab on click', async () => {
    vi.mocked(api.get).mockResolvedValue(CAMERA)
    renderPage()
    await screen.findByRole('heading', { name: 'Assembly Line 1' })
    fireEvent.click(screen.getByRole('tab', { name: 'Hardware' }))
    expect(screen.getByTestId('hardware-tab')).toBeInTheDocument()
  })

  it('switches to Overrides tab on click', async () => {
    vi.mocked(api.get).mockResolvedValue(CAMERA)
    renderPage()
    await screen.findByRole('heading', { name: 'Assembly Line 1' })
    fireEvent.click(screen.getByRole('tab', { name: 'Overrides' }))
    expect(screen.getByTestId('overrides-tab')).toBeInTheDocument()
  })

  it('renders HomographyCalibrator in Topology tab', async () => {
    vi.mocked(api.get).mockResolvedValue(CAMERA)
    renderPage()
    await screen.findByRole('heading', { name: 'Assembly Line 1' })
    fireEvent.click(screen.getByRole('tab', { name: 'Topology' }))
    expect(screen.getByTestId('homography-calibrator')).toBeInTheDocument()
  })

  it('shows capability tier in Profile tab', async () => {
    vi.mocked(api.get).mockResolvedValue(CAMERA)
    renderPage()
    await screen.findByText('FULL')
  })
})
