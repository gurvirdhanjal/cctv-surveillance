import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { ClipExportDialog } from './ClipExportDialog'
import * as client from '@/shared/api/client'

vi.mock('@/shared/api/client', () => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}))

const mockApi = vi.mocked(client.api)

beforeEach(() => {
  mockApi.post.mockResolvedValue({ ok: true })
})

function Wrapper({ children }: React.PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

describe('ClipExportDialog', () => {
  it('does not render when closed', () => {
    render(<ClipExportDialog open={false} onClose={vi.fn()} />, { wrapper: Wrapper })
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('renders when open', () => {
    render(<ClipExportDialog open={true} onClose={vi.fn()} cameraId={1} />, { wrapper: Wrapper })
    expect(screen.getByRole('dialog', { name: 'Export Clip' })).toBeInTheDocument()
  })

  it('prefills camera id from prop', () => {
    render(<ClipExportDialog open={true} onClose={vi.fn()} cameraId={42} />, { wrapper: Wrapper })
    expect(screen.getByLabelText('Camera ID')).toHaveValue(42)
  })

  it('format select defaults to MP4', () => {
    render(<ClipExportDialog open={true} onClose={vi.fn()} />, { wrapper: Wrapper })
    expect(screen.getByLabelText('Format')).toHaveValue('MP4')
  })

  it('format select can be changed to WebM', () => {
    render(<ClipExportDialog open={true} onClose={vi.fn()} />, { wrapper: Wrapper })
    fireEvent.change(screen.getByLabelText('Format'), { target: { value: 'WebM' } })
    expect(screen.getByLabelText('Format')).toHaveValue('WebM')
  })

  it('shows validation error when end <= start', async () => {
    render(<ClipExportDialog open={true} onClose={vi.fn()} cameraId={1} anchorMs={Date.now()} />, { wrapper: Wrapper })
    const endInput = screen.getByLabelText('End')
    // Set end to same as start (datetime-local values are equal)
    fireEvent.change(endInput, { target: { value: screen.getByLabelText<HTMLInputElement>('Start').value } })
    fireEvent.click(screen.getByRole('button', { name: 'Export' }))
    await waitFor(() => {
      expect(screen.getByText('End must be after start')).toBeInTheDocument()
    })
  })

  it('calls POST /api/forensic/export on valid submit', async () => {
    render(<ClipExportDialog open={true} onClose={vi.fn()} cameraId={1} anchorMs={Date.now()} />, { wrapper: Wrapper })
    fireEvent.click(screen.getByRole('button', { name: 'Export' }))
    await waitFor(() => {
      expect(mockApi.post).toHaveBeenCalledWith('/api/forensic/export', expect.objectContaining({
        camera_id: 1,
        format: 'MP4',
      }))
    })
  })
})
