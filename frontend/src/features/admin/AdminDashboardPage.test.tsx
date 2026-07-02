import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

vi.mock('@/shared/api/client', () => ({ api: { get: vi.fn() } }))

import { api } from '@/shared/api/client'
const { AdminDashboardPage } = await import('./AdminDashboardPage')

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage() {
  return render(
    <HelmetProvider>
      <QueryClientProvider client={makeClient()}>
        <MemoryRouter>
          <AdminDashboardPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

describe('AdminDashboardPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.get).mockResolvedValue({})
  })

  it('renders page heading', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: 'System Dashboard' })).toBeInTheDocument()
  })

  it('renders system health section', () => {
    renderPage()
    expect(screen.getByRole('region', { name: 'System health' })).toBeInTheDocument()
  })

  it('renders system metrics section', () => {
    renderPage()
    expect(screen.getByRole('region', { name: 'System metrics' })).toBeInTheDocument()
  })

  it('shows version from health response', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/api/health') return Promise.resolve({ status: 'ok', version: '1.4.2' })
      return Promise.resolve({})
    })
    renderPage()
    expect(await screen.findByText('1.4.2')).toBeInTheDocument()
  })

  it('shows OK badge when health status is ok', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/api/health') return Promise.resolve({ status: 'ok', version: '1.0.0' })
      if (url === '/api/ready') return Promise.resolve({ db: 'ok', redis: 'ok' })
      return Promise.resolve({})
    })
    renderPage()
    const badges = await screen.findAllByText('OK')
    expect(badges.length).toBeGreaterThanOrEqual(1)
  })

  it('shows FAIL badge when db is fail', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/api/health') return Promise.resolve({ status: 'ok', version: '1.0.0' })
      if (url === '/api/ready') return Promise.resolve({ db: 'fail', redis: 'ok' })
      return Promise.resolve({})
    })
    renderPage()
    expect(await screen.findByText('FAIL')).toBeInTheDocument()
  })
})
