import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/shared/api/client', () => ({ api: { delete: vi.fn() } }))

import { api } from '@/shared/api/client'
const { GdprDeleteDialog } = await import('./GdprDeleteDialog')

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderDialog(onConfirmed = vi.fn(), onCancel = vi.fn()) {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter>
        <GdprDeleteDialog
          personId={7}
          personName="Ranjeet Kumar"
          onConfirmed={onConfirmed}
          onCancel={onCancel}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('GdprDeleteDialog', () => {
  beforeEach(() => {
    vi.mocked(api.delete).mockReset()
  })

  it('renders dialog with person name', () => {
    renderDialog()
    expect(screen.getByRole('dialog', { name: 'GDPR person delete' })).toBeInTheDocument()
    const mentions = screen.getAllByText(/Ranjeet Kumar/)
    expect(mentions.length).toBeGreaterThanOrEqual(1)
  })

  it('Delete button is disabled initially', () => {
    renderDialog()
    expect(screen.getByRole('button', { name: 'Delete Person' })).toBeDisabled()
  })

  it('Delete button is disabled when name does not match', () => {
    renderDialog()
    fireEvent.change(screen.getByLabelText("Type the person's full name to confirm"), {
      target: { value: 'Wrong Name' },
    })
    fireEvent.change(screen.getByLabelText('Reason for deletion (min 10 characters)'), {
      target: { value: 'GDPR erasure request received on 2026-06-24' },
    })
    expect(screen.getByRole('button', { name: 'Delete Person' })).toBeDisabled()
  })

  it('Delete button is disabled when reason is too short', () => {
    renderDialog()
    fireEvent.change(screen.getByLabelText("Type the person's full name to confirm"), {
      target: { value: 'Ranjeet Kumar' },
    })
    fireEvent.change(screen.getByLabelText('Reason for deletion (min 10 characters)'), {
      target: { value: 'short' },
    })
    expect(screen.getByRole('button', { name: 'Delete Person' })).toBeDisabled()
  })

  it('Delete button is enabled when name matches and reason is long enough', () => {
    renderDialog()
    fireEvent.change(screen.getByLabelText("Type the person's full name to confirm"), {
      target: { value: 'Ranjeet Kumar' },
    })
    fireEvent.change(screen.getByLabelText('Reason for deletion (min 10 characters)'), {
      target: { value: 'GDPR erasure request received' },
    })
    expect(screen.getByRole('button', { name: 'Delete Person' })).not.toBeDisabled()
  })

  it('calls DELETE /api/persons/:id when confirmed', async () => {
    vi.mocked(api.delete).mockResolvedValue(undefined)
    const onConfirmed = vi.fn()
    renderDialog(onConfirmed)

    fireEvent.change(screen.getByLabelText("Type the person's full name to confirm"), {
      target: { value: 'Ranjeet Kumar' },
    })
    fireEvent.change(screen.getByLabelText('Reason for deletion (min 10 characters)'), {
      target: { value: 'GDPR erasure request received on 2026-06-24' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Delete Person' }))

    await waitFor(() => {
      expect(vi.mocked(api.delete)).toHaveBeenCalledWith('/api/persons/7', expect.any(Object))
    })
    expect(onConfirmed).toHaveBeenCalledOnce()
  })

  it('calls onCancel when Cancel is clicked', () => {
    const onCancel = vi.fn()
    renderDialog(vi.fn(), onCancel)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
