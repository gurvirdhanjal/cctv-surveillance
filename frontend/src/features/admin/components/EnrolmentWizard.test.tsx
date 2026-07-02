import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/shared/api/client', () => ({ api: { post: vi.fn() } }))

import { api } from '@/shared/api/client'
const { EnrolmentWizard } = await import('./EnrolmentWizard')

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
}

function renderWizard(onDone = vi.fn(), onCancel = vi.fn()) {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter>
        <EnrolmentWizard onDone={onDone} onCancel={onCancel} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('EnrolmentWizard', () => {
  beforeEach(() => {
    vi.mocked(api.post).mockReset()
  })

  it('renders step 1 by default', () => {
    renderWizard()
    expect(screen.getByLabelText('Personal info form')).toBeInTheDocument()
  })

  it('shows wizard step indicators', () => {
    renderWizard()
    const steps = screen.getByRole('list', { name: 'Wizard steps' })
    expect(steps).toBeInTheDocument()
    expect(screen.getByText('Personal Info')).toBeInTheDocument()
    expect(screen.getByText('Capture')).toBeInTheDocument()
    expect(screen.getByText('Quality Check')).toBeInTheDocument()
    expect(screen.getByText('Confirm')).toBeInTheDocument()
  })

  it('validates employee_id regex — rejects invalid format', async () => {
    renderWizard()
    fireEvent.input(screen.getByLabelText('Full name'), { target: { value: 'Jane Doe' } })
    fireEvent.input(screen.getByLabelText('Employee ID'), { target: { value: 'INVALID' } })
    fireEvent.submit(screen.getByLabelText('Personal info form'))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/Format: EMP-XXXXXX/)).toBeInTheDocument()
  })

  it('accepts valid employee_id EMP-001234', async () => {
    renderWizard()
    fireEvent.input(screen.getByLabelText('Full name'), { target: { value: 'Jane Doe' } })
    fireEvent.input(screen.getByLabelText('Employee ID'), { target: { value: 'EMP-001234' } })
    fireEvent.submit(screen.getByLabelText('Personal info form'))
    await waitFor(() => {
      expect(screen.getByText('Camera capture (simulated)')).toBeInTheDocument()
    })
  })

  it('advances to step 2 (Capture) after valid step 1', async () => {
    renderWizard()
    fireEvent.input(screen.getByLabelText('Full name'), { target: { value: 'Ranjeet Kumar' } })
    fireEvent.input(screen.getByLabelText('Employee ID'), { target: { value: 'EMP-999' } })
    fireEvent.submit(screen.getByLabelText('Personal info form'))
    await waitFor(() => {
      expect(screen.getByLabelText('Camera capture area')).toBeInTheDocument()
    })
  })

  it('calls onCancel when cancel is clicked with clean form', () => {
    const onCancel = vi.fn()
    renderWizard(vi.fn(), onCancel)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel enrolment' }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('calls POST /api/persons on final save step', async () => {
    vi.mocked(api.post).mockResolvedValue({ person_id: 42 })
    const onDone = vi.fn()
    renderWizard(onDone)

    // Step 1
    fireEvent.input(screen.getByLabelText('Full name'), { target: { value: 'Test Person' } })
    fireEvent.input(screen.getByLabelText('Employee ID'), { target: { value: 'EMP-123' } })
    fireEvent.submit(screen.getByLabelText('Personal info form'))

    // Step 2
    await waitFor(() => expect(screen.getByText('Next')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Next'))

    // Step 3
    await waitFor(() =>
      expect(screen.getByText(/Quality check passed/)).toBeInTheDocument(),
    )
    fireEvent.click(screen.getByText('Next'))

    // Step 4 - save
    await waitFor(() => expect(screen.getByText('Save')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Save'))

    await waitFor(() => {
      expect(vi.mocked(api.post)).toHaveBeenCalledWith('/api/persons', {
        name: 'Test Person',
        employee_id: 'EMP-123',
      })
    })
    expect(onDone).toHaveBeenCalledWith(42)
  })
})
