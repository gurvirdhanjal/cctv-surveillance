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

  it('renders icon variant (square 32px, no padding)', () => {
    render(<Button variant="icon" aria-label="Settings"><span>⚙</span></Button>)
    const btn = screen.getByRole('button', { name: 'Settings' })
    // icon variant applies h-8 w-8 p-0 (square, no text padding)
    expect(btn.className).toContain('h-8')
    expect(btn.className).toContain('w-8')
  })

  it('renders toolbar variant (32px height, sm radius)', () => {
    render(<Button variant="toolbar" aria-label="Filter">Filter</Button>)
    const btn = screen.getByRole('button', { name: 'Filter' })
    // toolbar variant applies h-8 rounded-sm
    expect(btn.className).toContain('h-8')
    expect(btn.className).toContain('rounded-sm')
  })

  it('renders split variant with onPrimary', async () => {
    const onPrimary = vi.fn()
    render(
      <Button variant="split" onPrimary={onPrimary} menuItems={[]}>
        Export
      </Button>
    )
    const btn = screen.getByRole('button', { name: /export/i })
    await userEvent.click(btn)
    expect(onPrimary).toHaveBeenCalledOnce()
  })

  it('focus ring uses --focus-ring (charcoal), not brand brass', () => {
    const { container } = render(<Button>Save</Button>)
    const btn = container.querySelector('button')!
    expect(btn.className).not.toMatch(/brand/)
    expect(btn.className).toContain('focus-ring') // maps to --focus-ring
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
