import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import axe from 'axe-core'
import { Button } from './Button'

describe('Button', () => {
  it('renders children', () => {
    render(<Button>Save</Button>)
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
  })

  it('calls onClick when clicked', async () => {
    const handleClick = vi.fn()
    render(<Button onClick={handleClick}>Click me</Button>)
    await userEvent.click(screen.getByRole('button'))
    expect(handleClick).toHaveBeenCalledOnce()
  })

  it('is disabled when disabled prop is set', () => {
    render(<Button disabled>Disabled</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('shows spinner and aria-busy when loading', () => {
    render(<Button loading>Save</Button>)
    const btn = screen.getByRole('button')
    expect(btn).toHaveAttribute('aria-busy', 'true')
    expect(btn).toBeDisabled()
  })

  it('loading button keeps its accessible name', () => {
    render(<Button loading>Save changes</Button>)
    expect(screen.getByRole('button', { name: /save changes/i })).toBeInTheDocument()
  })

  it('renders destructive variant', () => {
    render(<Button variant="destructive">Delete</Button>)
    const btn = screen.getByRole('button', { name: 'Delete' })
    expect(btn).toBeInTheDocument()
  })

  it('renders secondary variant', () => {
    render(<Button variant="secondary">Cancel</Button>)
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
  })

  it('is accessible (no axe violations)', async () => {
    const { container } = render(
      <div>
        <Button>Primary action</Button>
        <Button variant="secondary">Cancel</Button>
        <Button variant="destructive">Delete</Button>
      </div>,
    )
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })
})
