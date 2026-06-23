import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

vi.mock('@/shared/api/client', () => ({ api: { get: vi.fn() } }))

vi.mock('./components/KpiCard', () => ({
  KpiCard: ({ label }: { label: string }) => <div data-testid="kpi-card">{label}</div>,
}))

vi.mock('./components/HeadCountChart', () => ({
  HeadCountChart: () => <div data-testid="head-count-chart" />,
}))

vi.mock('./components/AlertVolumeChart', () => ({
  AlertVolumeChart: () => <div data-testid="alert-volume-chart" />,
}))

import { api } from '@/shared/api/client'

const { AnalyticsDashboardPage } = await import('./AnalyticsDashboardPage')

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage() {
  const client = makeClient()
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <AnalyticsDashboardPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

describe('AnalyticsDashboardPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockResolvedValue({})
  })

  it('renders page heading', () => {
    renderPage()
    expect(screen.getByText('Analytics Dashboard')).toBeInTheDocument()
  })

  it('renders 4 KPI cards', () => {
    renderPage()
    expect(screen.getAllByTestId('kpi-card')).toHaveLength(4)
  })

  it('renders head count and alert volume charts', () => {
    renderPage()
    expect(screen.getByTestId('head-count-chart')).toBeInTheDocument()
    expect(screen.getByTestId('alert-volume-chart')).toBeInTheDocument()
  })

  it('renders quick action links', () => {
    renderPage()
    expect(screen.getByRole('link', { name: 'Open Timeline' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'View Heatmap' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Forensic Search' })).toBeInTheDocument()
  })

  it('renders key metrics and charts sections', () => {
    renderPage()
    expect(screen.getByRole('region', { name: 'Key metrics' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Charts' })).toBeInTheDocument()
  })
})
