import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

vi.mock('@/shared/api/client', () => ({ api: { get: vi.fn() } }))

vi.mock('./components/ClipResultCard', () => ({
  ClipResultCard: ({ clip }: { clip: { global_track_id: string } }) => (
    <div data-testid="clip-card">{clip.global_track_id}</div>
  ),
}))

vi.mock('./components/ClipDrawer', () => ({
  ClipDrawer: ({ onClose }: { onClose: () => void }) => (
    <div data-testid="clip-drawer">
      <button onClick={onClose}>close</button>
    </div>
  ),
}))

import { api } from '@/shared/api/client'
import { NotImplementedError } from '@/shared/api/errors'
import type { ForensicClip } from '@/shared/api/types'

const { ForensicSearchPage } = await import('./ForensicSearchPage')

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderPage() {
  const client = makeClient()
  return render(
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <ForensicSearchPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

describe('ForensicSearchPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  it('renders page heading and search form', () => {
    renderPage()
    expect(screen.getByText('Forensic Search')).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Forensic search form' })).toBeInTheDocument()
  })

  it('renders search query text input', () => {
    renderPage()
    expect(screen.getByRole('textbox', { name: 'Search query' })).toBeInTheDocument()
  })

  it('shows unavailable notice when 501 is returned', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new NotImplementedError())
    renderPage()
    const input = screen.getByRole('textbox', { name: 'Search query' })
    fireEvent.change(input, { target: { value: 'person in yellow vest' } })
    fireEvent.submit(screen.getByRole('form', { name: 'Forensic search form' }))
    expect(await screen.findByRole('status', { name: 'Search unavailable' })).toBeInTheDocument()
  })

  it('shows clip cards when results are returned', async () => {
    const clips: ForensicClip[] = [
      {
        global_track_id: 'track-1',
        camera_id: 1,
        zone_id: null,
        score: 0.9,
        triggered_at: '2026-06-24T09:00:00Z',
        thumbnail_url: null,
        clip_url: null,
        duration_s: null,
        alert_id: null,
      },
    ]
    vi.mocked(api.get).mockResolvedValueOnce(clips)
    renderPage()
    const input = screen.getByRole('textbox', { name: 'Search query' })
    fireEvent.change(input, { target: { value: 'yellow vest' } })
    fireEvent.submit(screen.getByRole('form', { name: 'Forensic search form' }))
    expect(await screen.findAllByTestId('clip-card')).toHaveLength(1)
  })

  it('shows empty state when no results', async () => {
    vi.mocked(api.get).mockResolvedValueOnce([])
    renderPage()
    const input = screen.getByRole('textbox', { name: 'Search query' })
    fireEvent.change(input, { target: { value: 'blue hard hat' } })
    fireEvent.submit(screen.getByRole('form', { name: 'Forensic search form' }))
    expect(await screen.findByText(/No results found/)).toBeInTheDocument()
  })
})
