import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Modal } from './Modal'

function TestModal({ open = true, onClose = vi.fn() } = {}) {
  return (
    <Modal open={open} onClose={onClose} title="Confirm action">
      <p>Are you sure?</p>
    </Modal>
  )
}

describe('Modal', () => {
  it('renders title when open', () => {
    render(<TestModal />)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Confirm action')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    render(<TestModal open={false} />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('calls onClose when Escape is pressed', async () => {
    const onClose = vi.fn()
    render(<TestModal onClose={onClose} />)
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when the close button is clicked', async () => {
    const onClose = vi.fn()
    render(<TestModal onClose={onClose} />)
    await userEvent.click(screen.getByRole('button', { name: 'Close dialog' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('has a dialog role with an accessible name', () => {
    render(<TestModal />)
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()
    const heading = within(dialog).getByText('Confirm action')
    expect(heading).toBeInTheDocument()
  })

  it('renders description when provided', () => {
    render(
      <Modal open onClose={vi.fn()} title="Delete zone" description="This action cannot be undone.">
        <p>body</p>
      </Modal>,
    )
    expect(screen.getByText('This action cannot be undone.')).toBeInTheDocument()
  })
})
