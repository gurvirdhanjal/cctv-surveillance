import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider, type ToastItem } from './Toast'

const successToast: ToastItem = {
  id: '1',
  severity: 'success',
  title: 'Zone saved',
  description: 'Loading Bay has been updated.',
}

const errorToast: ToastItem = {
  id: '2',
  severity: 'error',
  title: 'Save failed',
}

describe('Toast', () => {
  it('renders toast title', () => {
    render(<ToastProvider toasts={[successToast]} onDismiss={vi.fn()} />)
    expect(screen.getByText('Zone saved')).toBeInTheDocument()
  })

  it('renders description when provided', () => {
    render(<ToastProvider toasts={[successToast]} onDismiss={vi.fn()} />)
    expect(screen.getByText('Loading Bay has been updated.')).toBeInTheDocument()
  })

  it('error toast uses aria-live=assertive for immediate announcement', () => {
    const { container } = render(
      <ToastProvider toasts={[errorToast]} onDismiss={vi.fn()} />,
    )
    const toast = container.querySelector('[aria-live="assertive"]')
    expect(toast).toBeInTheDocument()
  })

  it('success toast uses aria-live=polite', () => {
    const { container } = render(
      <ToastProvider toasts={[successToast]} onDismiss={vi.fn()} />,
    )
    const toast = container.querySelector('[aria-live="polite"]')
    expect(toast).toBeInTheDocument()
  })

  it('calls onDismiss when dismiss button is clicked', async () => {
    const onDismiss = vi.fn()
    render(<ToastProvider toasts={[successToast]} onDismiss={onDismiss} />)
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss notification' }))
    expect(onDismiss).toHaveBeenCalledWith('1')
  })

  it('renders multiple toasts', () => {
    render(<ToastProvider toasts={[successToast, errorToast]} onDismiss={vi.fn()} />)
    expect(screen.getByText('Zone saved')).toBeInTheDocument()
    expect(screen.getByText('Save failed')).toBeInTheDocument()
  })
})
