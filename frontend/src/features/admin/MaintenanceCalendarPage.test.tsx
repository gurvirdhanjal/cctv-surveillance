import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

vi.mock('@/shared/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

vi.mock('cron-parser', () => ({
  parseExpression: vi.fn(() => {
    let count = 0
    return {
      next: () => ({ toDate: () => new Date(2026, 6, 1 + count++, 2, 0, 0) }),
    }
  }),
}))

import { api } from '@/shared/api/client'
const { MaintenanceCalendarPage } = await import('./MaintenanceCalendarPage')

const WINDOWS = [
  {
    window_id: 1,
    name: 'Nightly backup',
    scope_type: 'CAMERA',
    scope_id: 1,
    schedule_type: 'RECURRING',
    starts_at: null,
    ends_at: null,
    cron_expr: '0 2 * * *',
    duration_minutes: 60,
    suppress_alert_types: null,
    is_active: true,
    reason: null,
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
          <MaintenanceCalendarPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

describe('MaintenanceCalendarPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.post).mockReset()
    vi.mocked(api.delete).mockReset()
  })

  it('renders page heading', () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    expect(screen.getByRole('heading', { name: 'Maintenance Windows' })).toBeInTheDocument()
  })

  it('renders windows list', async () => {
    vi.mocked(api.get).mockResolvedValue(WINDOWS)
    renderPage()
    expect(await screen.findByText('Nightly backup')).toBeInTheDocument()
    expect(screen.getByText('0 2 * * *')).toBeInTheDocument()
  })

  it('opens Schedule Window dialog', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Schedule Window' }))
    expect(
      await screen.findByRole('dialog', { name: 'Schedule maintenance window' }),
    ).toBeInTheDocument()
  })

  it('shows ONE_TIME fields by default', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Schedule Window' }))
    await screen.findByRole('dialog')
    expect(screen.getByLabelText('Start')).toBeInTheDocument()
    expect(screen.getByLabelText('End')).toBeInTheDocument()
  })

  it('switches to RECURRING fields when Recurring is pressed', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Schedule Window' }))
    await screen.findByRole('dialog')
    fireEvent.click(screen.getByRole('button', { name: 'Recurring' }))
    expect(screen.getByLabelText('Cron expression')).toBeInTheDocument()
    expect(screen.getByLabelText('Duration (minutes)')).toBeInTheDocument()
  })

  it('shows next 3 firings for valid cron expression', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    const user = userEvent.setup()
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Schedule Window' }))
    await screen.findByRole('dialog')
    fireEvent.click(screen.getByRole('button', { name: 'Recurring' }))
    await screen.findByLabelText('Cron expression')
    await user.type(screen.getByLabelText('Cron expression'), '0 2 * * *')
    const list = await screen.findByRole('list', { name: 'Next 3 firings' }, { timeout: 3000 })
    expect(within(list).getAllByRole('listitem').length).toBe(3)
  })

  it('ONE_TIME button is initially pressed', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Schedule Window' }))
    await screen.findByRole('dialog')
    expect(screen.getByRole('button', { name: 'One-time' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })
})
