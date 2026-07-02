import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

vi.mock('@tanstack/react-virtual', () => ({
  useVirtualizer: vi.fn(({ count }: { count: number }) => ({
    getVirtualItems: () =>
      Array.from({ length: count }, (_, i) => ({
        key: i,
        index: i,
        start: i * 52,
        size: 52,
      })),
    getTotalSize: () => count * 52,
    measureElement: vi.fn(),
  })),
}))

vi.mock('@/shared/api/client', () => ({ api: { get: vi.fn() } }))

vi.mock('./components/EnrolmentWizard', () => ({
  EnrolmentWizard: ({ onCancel }: { onCancel: () => void }) => (
    <div data-testid="enrolment-wizard">
      <button onClick={onCancel}>close-wizard</button>
    </div>
  ),
}))

vi.mock('./components/GdprDeleteDialog', () => ({
  GdprDeleteDialog: ({ onCancel }: { onCancel: () => void }) => (
    <div data-testid="gdpr-dialog">
      <button onClick={onCancel}>close-delete</button>
    </div>
  ),
}))

import { api } from '@/shared/api/client'
const { AdminPersonsPage } = await import('./AdminPersonsPage')

const PERSONS = [
  { person_id: 1, name: 'Alice Smith', employee_id: 'EMP-001', is_active: true },
  { person_id: 2, name: 'Bob Jones', employee_id: 'EMP-002', is_active: false },
]

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage() {
  return render(
    <HelmetProvider>
      <QueryClientProvider client={makeClient()}>
        <MemoryRouter>
          <AdminPersonsPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

describe('AdminPersonsPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  it('renders page heading and search input', () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    expect(screen.getByRole('heading', { name: 'Persons' })).toBeInTheDocument()
    expect(screen.getByRole('searchbox', { name: 'Search persons' })).toBeInTheDocument()
  })

  it('renders Enrol Person button', () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    expect(screen.getByRole('button', { name: 'Enrol Person' })).toBeInTheDocument()
  })

  it('renders persons list', async () => {
    vi.mocked(api.get).mockResolvedValue(PERSONS)
    renderPage()
    expect(await screen.findByText('Alice Smith')).toBeInTheDocument()
    expect(screen.getByText('Bob Jones')).toBeInTheDocument()
  })

  it('shows active/inactive badges', async () => {
    vi.mocked(api.get).mockResolvedValue(PERSONS)
    renderPage()
    expect(await screen.findByText('Active')).toBeInTheDocument()
    expect(screen.getByText('Inactive')).toBeInTheDocument()
  })

  it('opens EnrolmentWizard when Enrol Person clicked', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Enrol Person' }))
    expect(await screen.findByTestId('enrolment-wizard')).toBeInTheDocument()
  })

  it('opens GdprDeleteDialog when Delete clicked', async () => {
    vi.mocked(api.get).mockResolvedValue(PERSONS)
    renderPage()
    const deleteBtn = await screen.findByRole('button', { name: 'Delete Alice Smith' })
    fireEvent.click(deleteBtn)
    expect(await screen.findByTestId('gdpr-dialog')).toBeInTheDocument()
  })

  it('shows empty state when no persons', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    expect(await screen.findByText('No persons found.')).toBeInTheDocument()
  })

  it('shows error state when fetch fails', async () => {
    vi.mocked(api.get).mockRejectedValue(new Error('Network error'))
    renderPage()
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
