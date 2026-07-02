import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

vi.mock('@/shared/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import { api } from '@/shared/api/client'
const { ZoneEditorPage } = await import('./ZoneEditorPage')

const ZONES = [
  {
    zone_id: 1,
    name: 'Assembly',
    polygon: null,
    allowed_hours: null,
    max_capacity: 20,
    loiter_threshold_s: 30,
    floor_plan_id: null,
    is_active: true,
  },
  {
    zone_id: 2,
    name: 'Entrance',
    polygon: null,
    allowed_hours: '08:00-18:00',
    max_capacity: null,
    loiter_threshold_s: 60,
    floor_plan_id: null,
    is_active: true,
  },
]

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderPage() {
  return render(
    <HelmetProvider>
      <QueryClientProvider client={makeClient()}>
        <MemoryRouter>
          <ZoneEditorPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

describe('ZoneEditorPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.patch).mockReset()
    vi.mocked(api.delete).mockReset()
  })

  it('renders page heading', () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    expect(screen.getByRole('heading', { name: 'Zones' })).toBeInTheDocument()
  })

  it('renders zone list', async () => {
    vi.mocked(api.get).mockResolvedValue(ZONES)
    renderPage()
    expect(await screen.findByText('Assembly')).toBeInTheDocument()
    expect(screen.getByText('Entrance')).toBeInTheDocument()
  })

  it('renders Edit and Delete buttons per zone', async () => {
    vi.mocked(api.get).mockResolvedValue(ZONES)
    renderPage()
    expect(await screen.findByRole('button', { name: 'Edit Assembly' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete Assembly' })).toBeInTheDocument()
  })

  it('opens Add Zone dialog', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Add Zone' }))
    expect(await screen.findByRole('dialog', { name: 'Add zone' })).toBeInTheDocument()
  })

  it('opens Edit dialog on Edit button click', async () => {
    vi.mocked(api.get).mockResolvedValue(ZONES)
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Edit Assembly' }))
    expect(screen.getByRole('dialog', { name: 'Edit Assembly' })).toBeInTheDocument()
  })

  it('opens Delete confirmation requiring typed name', async () => {
    vi.mocked(api.get).mockResolvedValue(ZONES)
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Delete Assembly' }))
    expect(screen.getByRole('dialog', { name: 'Confirm delete Assembly' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled()
  })

  it('enables Delete button after typing zone name', async () => {
    vi.mocked(api.get).mockResolvedValue(ZONES)
    vi.mocked(api.delete).mockResolvedValue(undefined)
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Delete Assembly' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Type zone name to confirm' }), {
      target: { value: 'Assembly' },
    })
    expect(screen.getByRole('button', { name: 'Delete' })).not.toBeDisabled()
  })

  it('calls DELETE /api/zones/:id on confirm', async () => {
    vi.mocked(api.get).mockResolvedValue(ZONES)
    vi.mocked(api.delete).mockResolvedValue(undefined)
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Delete Assembly' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Type zone name to confirm' }), {
      target: { value: 'Assembly' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    await waitFor(() => {
      expect(vi.mocked(api.delete)).toHaveBeenCalledWith('/api/zones/1')
    })
  })
})
