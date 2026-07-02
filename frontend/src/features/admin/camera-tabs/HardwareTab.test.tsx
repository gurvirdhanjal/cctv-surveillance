import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/shared/api/client', () => ({ api: { get: vi.fn(), post: vi.fn() } }))

import { api } from '@/shared/api/client'
const { HardwareTab } = await import('./HardwareTab')

const PROFILE = {
  camera_id: 3,
  capability_tier: 'FULL',
  shutter_type: 'rolling',
  tier_reason: null,
  profiled_at: '2026-06-24T10:00:00Z',
  profile_data: {
    resolution_w: 1920,
    resolution_h: 1080,
    fps_measured: 29.5,
    focus_score: 0.87,
    frame_drop_rate: 0.02,
    brightness_mean: 0.6,
    shutter_suggestion: 'rolling',
    shutter_confidence: 0.9,
    suggested_tier: 'FULL',
    tier_reason: 'high fps + resolution',
  },
}

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderTab() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter>
        <HardwareTab cameraId={3} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('HardwareTab', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
  })

  it('renders Run Profiler button', async () => {
    vi.mocked(api.get).mockResolvedValue(PROFILE)
    renderTab()
    expect(await screen.findByRole('button', { name: 'Run Profiler' })).toBeInTheDocument()
  })

  it('shows confirmation dialog when Run Profiler clicked', async () => {
    vi.mocked(api.get).mockResolvedValue(PROFILE)
    renderTab()
    await screen.findByRole('button', { name: 'Run Profiler' })
    fireEvent.click(screen.getByRole('button', { name: 'Run Profiler' }))
    expect(screen.getByRole('dialog', { name: 'Confirm profiler run' })).toBeInTheDocument()
  })

  it('cancels confirmation dialog', async () => {
    vi.mocked(api.get).mockResolvedValue(PROFILE)
    renderTab()
    await screen.findByRole('button', { name: 'Run Profiler' })
    fireEvent.click(screen.getByRole('button', { name: 'Run Profiler' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog', { name: 'Confirm profiler run' })).not.toBeInTheDocument()
  })

  it('calls POST /api/cameras/:id/profile on confirm', async () => {
    vi.mocked(api.get).mockResolvedValue(PROFILE)
    vi.mocked(api.post).mockResolvedValue({})
    renderTab()
    await screen.findByRole('button', { name: 'Run Profiler' })
    fireEvent.click(screen.getByRole('button', { name: 'Run Profiler' }))
    fireEvent.click(screen.getByRole('button', { name: 'Run' }))
    await waitFor(() => {
      expect(vi.mocked(api.post)).toHaveBeenCalledWith('/api/cameras/3/profile', {})
    })
  })

  it('renders profile data when available', async () => {
    vi.mocked(api.get).mockResolvedValue(PROFILE)
    renderTab()
    expect(await screen.findByText('1920×1080')).toBeInTheDocument()
    expect(screen.getByText('29.5 fps')).toBeInTheDocument()
  })

  it('shows placeholder when no profile data', async () => {
    vi.mocked(api.get).mockResolvedValue({ ...PROFILE, profile_data: null })
    renderTab()
    expect(await screen.findByText(/No profile data yet/)).toBeInTheDocument()
  })
})
