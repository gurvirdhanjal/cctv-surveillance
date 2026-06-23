import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

vi.mock('@/shared/api/client', () => ({ api: { get: vi.fn() } }))

vi.mock('./components/DwellChart', () => ({
  DwellChart: () => <div data-testid="dwell-chart" />,
}))

vi.mock('./components/PersonTimeline', () => ({
  PersonTimeline: () => <div data-testid="person-timeline" />,
}))

import { api } from '@/shared/api/client'

const { PersonProfilePage } = await import('./PersonProfilePage')

const mockPerson = {
  person_id: 42,
  name: 'Alice Smith',
  employee_id: 'EMP-001',
  is_active: true,
  department: 'Engineering',
  last_seen_at: '2026-06-24T10:00:00Z',
  last_seen_camera_id: 3,
  thumbnail_url: null,
}

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage(personId = '42') {
  const client = makeClient()
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[`/analytics/persons/${personId}`]}>
          <Routes>
            <Route path="/analytics/persons/:id" element={<PersonProfilePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

describe('PersonProfilePage', () => {
  it('renders loading state initially', () => {
    vi.mocked(api.get).mockImplementation(() => new Promise(() => {}))
    renderPage()
    expect(screen.getByRole('status', { name: 'Loading profile' })).toBeInTheDocument()
  })

  it('renders person name when loaded', async () => {
    vi.mocked(api.get).mockResolvedValueOnce(mockPerson).mockResolvedValueOnce({ items: [] })
    renderPage()
    expect(await screen.findByText('Alice Smith')).toBeInTheDocument()
  })

  it('shows employee_id and department', async () => {
    vi.mocked(api.get).mockResolvedValueOnce(mockPerson).mockResolvedValueOnce({ items: [] })
    renderPage()
    await screen.findByText('Alice Smith')
    expect(screen.getByText(/EMP-001/)).toBeInTheDocument()
    expect(screen.getByText(/Engineering/)).toBeInTheDocument()
  })

  it('shows error state on fetch failure', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new Error('not found'))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load person profile')
  })

  it('renders dwell chart and timeline after load', async () => {
    vi.mocked(api.get).mockResolvedValueOnce(mockPerson).mockResolvedValueOnce({ items: [] })
    renderPage()
    await screen.findByText('Alice Smith')
    expect(screen.getByTestId('dwell-chart')).toBeInTheDocument()
    expect(screen.getByTestId('person-timeline')).toBeInTheDocument()
  })

  it('renders fallback avatar initial when no thumbnail', async () => {
    vi.mocked(api.get).mockResolvedValueOnce(mockPerson).mockResolvedValueOnce({ items: [] })
    renderPage()
    await screen.findByText('Alice Smith')
    expect(screen.getByText('A')).toBeInTheDocument()
  })

  it('renders "open in timeline scrubber" CTA', async () => {
    vi.mocked(api.get).mockResolvedValueOnce(mockPerson).mockResolvedValueOnce({ items: [] })
    renderPage()
    await screen.findByText('Alice Smith')
    expect(screen.getByRole('link', { name: 'Open in timeline scrubber' })).toBeInTheDocument()
  })
})
