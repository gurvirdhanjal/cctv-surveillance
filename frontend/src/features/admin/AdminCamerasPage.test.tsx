import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

vi.mock('@/shared/api/client', () => ({ api: { get: vi.fn(), post: vi.fn() } }))

import { api } from '@/shared/api/client'
const { AdminCamerasPage } = await import('./AdminCamerasPage')

const CAMERAS = [
  {
    camera_id: 1,
    name: 'Assembly Line 1',
    rtsp_url: 'rtsp://cam1/stream',
    is_active: true,
    capability_tier: 'FULL',
    shutter_type: 'rolling',
    profile_data: null,
    profiled_at: null,
    model_overrides: null,
    worker_group: null,
    recalibrate_required_at: null,
  },
  {
    camera_id: 2,
    name: 'Entrance',
    rtsp_url: 'rtsp://cam2/stream',
    is_active: false,
    capability_tier: 'LOW',
    shutter_type: 'unknown',
    profile_data: null,
    profiled_at: null,
    model_overrides: null,
    worker_group: null,
    recalibrate_required_at: null,
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
          <AdminCamerasPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

describe('AdminCamerasPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
  })

  it('renders page heading', () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    expect(screen.getByRole('heading', { name: 'Cameras' })).toBeInTheDocument()
  })

  it('renders camera list with tier badges', async () => {
    vi.mocked(api.get).mockResolvedValue(CAMERAS)
    renderPage()
    expect(await screen.findByText('Assembly Line 1')).toBeInTheDocument()
    expect(screen.getByTestId('tier-badge-1')).toHaveTextContent('FULL')
    expect(screen.getByTestId('tier-badge-2')).toHaveTextContent('LOW')
  })

  it('renders Settings link for each camera', async () => {
    vi.mocked(api.get).mockResolvedValue(CAMERAS)
    renderPage()
    expect(
      await screen.findByRole('link', { name: 'Settings Assembly Line 1' }),
    ).toBeInTheDocument()
  })

  it('opens add-camera dialog when Add Camera clicked', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Add Camera' }))
    expect(await screen.findByRole('dialog', { name: 'Add camera' })).toBeInTheDocument()
  })

  it('validates camera name is required', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Add Camera' }))
    await screen.findByRole('dialog', { name: 'Add camera' })
    fireEvent.submit(screen.getByLabelText('Add camera form'))
    const alerts = await screen.findAllByRole('alert')
    expect(alerts.length).toBeGreaterThanOrEqual(1)
  })

  it('validates IP address format', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    const user = userEvent.setup()
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Add Camera' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add camera' })
    await user.type(within(dialog).getByLabelText('Camera name'), 'Test Cam')
    await user.type(within(dialog).getByLabelText('IP address'), 'not-an-ip')
    await user.type(within(dialog).getByLabelText('Username'), 'admin')
    await user.type(within(dialog).getByLabelText('Password'), 'pass')
    fireEvent.submit(screen.getByLabelText('Add camera form'))
    expect(await screen.findByText(/valid IP/)).toBeInTheDocument()
  })

  it('calls POST /api/cameras/from-credentials on valid form submit', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    vi.mocked(api.post).mockResolvedValue({ camera_id: 99 })
    const user = userEvent.setup()
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Add Camera' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add camera' })
    await user.type(within(dialog).getByLabelText('Camera name'), 'New Camera')
    await user.type(within(dialog).getByLabelText('IP address'), '192.168.1.50')
    await user.type(within(dialog).getByLabelText('Username'), 'admin')
    await user.type(within(dialog).getByLabelText('Password'), 'secret')
    await user.click(within(dialog).getByRole('button', { name: 'Add Camera' }))
    await waitFor(() => {
      expect(vi.mocked(api.post)).toHaveBeenCalledWith(
        '/api/cameras/from-credentials',
        expect.objectContaining({ host: '192.168.1.50', username: 'admin' }),
      )
    })
  })
})
