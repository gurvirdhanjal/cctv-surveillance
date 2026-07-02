import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/shared/api/client', () => ({ api: { get: vi.fn(), patch: vi.fn() } }))

import { api } from '@/shared/api/client'
const { OverridesTab } = await import('./OverridesTab')

const CONFIG_WITH_OVERRIDES = {
  camera_id: 3,
  settings: {
    scrfd_conf: { value: 0.7, source: 'camera_override' },
    shutter_correction: { value: true, source: 'camera_override' },
    adaface_min_sim: { value: 0.72, source: 'global_default' },
  },
}

const CONFIG_NO_OVERRIDES = {
  camera_id: 3,
  settings: {
    adaface_min_sim: { value: 0.72, source: 'global_default' },
    scrfd_conf: { value: 0.5, source: 'global_default' },
  },
}

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderTab(config = CONFIG_WITH_OVERRIDES) {
  vi.mocked(api.get).mockResolvedValue(config)
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter>
        <OverridesTab cameraId={3} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('OverridesTab', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.patch).mockReset()
  })

  it('filters out global_default settings', async () => {
    renderTab()
    await screen.findByText('scrfd_conf')
    expect(screen.queryByText('adaface_min_sim')).not.toBeInTheDocument()
  })

  it('shows amber banner when shutter override is present', async () => {
    renderTab()
    expect(
      await screen.findByRole('status', { name: 'Shutter override warning' }),
    ).toBeInTheDocument()
  })

  it('does not show amber banner when no shutter override', async () => {
    vi.mocked(api.get).mockResolvedValue({
      camera_id: 3,
      settings: {
        scrfd_conf: { value: 0.7, source: 'camera_override' },
      },
    })
    render(
      <QueryClientProvider client={makeClient()}>
        <MemoryRouter>
          <OverridesTab cameraId={3} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await screen.findByText('scrfd_conf')
    expect(
      screen.queryByRole('status', { name: 'Shutter override warning' }),
    ).not.toBeInTheDocument()
  })

  it('shows empty state when no overrides', async () => {
    renderTab(CONFIG_NO_OVERRIDES)
    expect(await screen.findByText(/No overrides set/)).toBeInTheDocument()
  })

  it('shows Add override form when button clicked', async () => {
    renderTab()
    await screen.findByText('scrfd_conf')
    fireEvent.click(screen.getByRole('button', { name: 'Add override' }))
    expect(screen.getByLabelText('Key')).toBeInTheDocument()
    expect(screen.getByLabelText('Value (JSON)')).toBeInTheDocument()
  })

  it('shows error when key is empty on save', async () => {
    renderTab()
    await screen.findByText('scrfd_conf')
    fireEvent.click(screen.getByRole('button', { name: 'Add override' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
