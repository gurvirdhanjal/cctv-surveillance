import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

vi.mock('@/shared/api/client', () => ({ api: { get: vi.fn() } }))

import { api } from '@/shared/api/client'
const { AuditLogViewerPage } = await import('./AuditLogViewerPage')

const ENTRIES = [
  {
    log_id: 1,
    event_type: 'PERSON_ENROLLED',
    actor_user_id: 2,
    actor_role: 'admin',
    subject_table: 'persons',
    subject_id: '42',
    detail: null,
    created_at: '2026-06-24T09:00:00Z',
    row_hash: 'abc123def456abc123def456abc123def456abc123def456abc123def456abc1',
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
          <AuditLogViewerPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

describe('AuditLogViewerPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  it('renders page heading', () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    expect(screen.getByRole('heading', { name: 'Audit Log' })).toBeInTheDocument()
  })

  it('renders Verify Chain and Export PDF buttons', () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    expect(screen.getByRole('button', { name: 'Verify Chain' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Export audit log PDF' })).toBeInTheDocument()
  })

  it('renders audit entries', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url.includes('/api/audit')) return Promise.resolve(ENTRIES)
      return Promise.resolve([])
    })
    renderPage()
    expect(await screen.findByText('PERSON_ENROLLED')).toBeInTheDocument()
    expect(screen.getByText('admin#2')).toBeInTheDocument()
  })

  it('shows chain intact message after verify with no break', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/api/audit/verify')
        return Promise.resolve({ rows_checked: 100, broken_chain_at: null })
      return Promise.resolve(ENTRIES)
    })
    renderPage()
    await screen.findByText('PERSON_ENROLLED')
    fireEvent.click(screen.getByRole('button', { name: 'Verify Chain' }))
    expect(
      await screen.findByRole('status', { name: 'Chain verification result' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Chain intact/)).toBeInTheDocument()
    expect(screen.getByText(/100 rows verified/)).toBeInTheDocument()
  })

  it('shows chain broken message with log_id when chain is broken', async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === '/api/audit/verify')
        return Promise.resolve({ rows_checked: 50, broken_chain_at: '47' })
      return Promise.resolve(ENTRIES)
    })
    renderPage()
    await screen.findByText('PERSON_ENROLLED')
    fireEvent.click(screen.getByRole('button', { name: 'Verify Chain' }))
    expect(await screen.findByText(/Chain broken at log_id/)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('47')).toBeInTheDocument()
    })
  })

  it('shows empty state when no entries', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    expect(await screen.findByText('No audit entries found.')).toBeInTheDocument()
  })
})
