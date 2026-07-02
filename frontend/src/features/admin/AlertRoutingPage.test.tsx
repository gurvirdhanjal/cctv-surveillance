import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

vi.mock('@/shared/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

import { api } from '@/shared/api/client'
const { AlertRoutingPage } = await import('./AlertRoutingPage')

const RULES = [
  {
    routing_id: 1,
    alert_type: 'INTRUSION',
    severity: 'HIGH',
    zone_id: null,
    channel: 'email',
    target: 'security@plant.com',
    is_active: true,
  },
  {
    routing_id: 2,
    alert_type: null,
    severity: null,
    zone_id: null,
    channel: 'webhook',
    target: 'https://hooks.example.com/vms',
    is_active: false,
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
          <AlertRoutingPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

describe('AlertRoutingPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.patch).mockReset()
    vi.mocked(api.delete).mockReset()
  })

  it('renders page heading', () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    expect(screen.getByRole('heading', { name: 'Alert Routing' })).toBeInTheDocument()
  })

  it('renders routing rules', async () => {
    vi.mocked(api.get).mockResolvedValue(RULES)
    renderPage()
    expect(await screen.findByText('email')).toBeInTheDocument()
    expect(screen.getByText('webhook')).toBeInTheDocument()
  })

  it('opens Add Rule dialog', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Add Rule' }))
    expect(await screen.findByRole('dialog', { name: 'Add routing rule' })).toBeInTheDocument()
  })

  it('validates webhook target must be https://', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Add Rule' }))
    await screen.findByRole('dialog')
    fireEvent.change(screen.getByLabelText('Channel'), { target: { value: 'webhook' } })
    fireEvent.input(screen.getByLabelText(/Target/), {
      target: { value: 'http://insecure.example.com/webhook' },
    })
    fireEvent.submit(screen.getByLabelText('Add routing rule form'))
    expect(await screen.findByText(/must start with https/)).toBeInTheDocument()
  })

  it('calls POST /api/alert-routing on valid form', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    vi.mocked(api.post).mockResolvedValue({ routing_id: 3 })
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Add Rule' }))
    await screen.findByRole('dialog')
    fireEvent.change(screen.getByLabelText('Channel'), { target: { value: 'email' } })
    fireEvent.input(screen.getByLabelText(/Target/), {
      target: { value: 'ops@company.com' },
    })
    fireEvent.submit(screen.getByLabelText('Add routing rule form'))
    await waitFor(() => {
      expect(vi.mocked(api.post)).toHaveBeenCalledWith(
        '/api/alert-routing',
        expect.objectContaining({ channel: 'email', target: 'ops@company.com' }),
      )
    })
  })

  it('calls PATCH to toggle rule active state', async () => {
    vi.mocked(api.get).mockResolvedValue(RULES)
    vi.mocked(api.patch).mockResolvedValue({})
    renderPage()
    const toggle = await screen.findByRole('switch', { name: 'Deactivate rule 1' })
    fireEvent.click(toggle)
    await waitFor(() => {
      expect(vi.mocked(api.patch)).toHaveBeenCalledWith('/api/alert-routing/1', {
        is_active: false,
      })
    })
  })
})
