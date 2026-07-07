import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ActionBar } from './ActionBar'
import { Button } from './Button'

describe('ActionBar (§S)', () => {
  it('renders with role="toolbar"', () => {
    render(<ActionBar aria-label="Page actions" />)
    expect(screen.getByRole('toolbar')).toBeInTheDocument()
  })

  it('requires aria-label for accessibility', () => {
    render(<ActionBar aria-label="Camera actions" />)
    expect(screen.getByRole('toolbar', { name: 'Camera actions' })).toBeInTheDocument()
  })

  it('renders left slot content', () => {
    render(<ActionBar aria-label="x" left={<span>Page title</span>} />)
    expect(screen.getByText('Page title')).toBeInTheDocument()
  })

  it('renders right slot content', () => {
    render(<ActionBar aria-label="x" right={<Button>Add Item</Button>} />)
    expect(screen.getByRole('button', { name: 'Add Item' })).toBeInTheDocument()
  })

  it('renders both slots in a flex row', () => {
    const { container } = render(
      <ActionBar aria-label="x" left={<span>Left</span>} right={<span>Right</span>} />
    )
    const root = container.firstChild as HTMLElement
    expect(root.className).toContain('flex')
  })

  it('applies toolbar elevation classes (z-toolbar + shadow-2)', () => {
    const { container } = render(<ActionBar aria-label="x" />)
    const root = container.firstChild as HTMLElement
    expect(root.className).toContain('z-toolbar')
    expect(root.className).toContain('shadow-2')
  })

  it('sticky prop adds sticky top-0', () => {
    const { container } = render(<ActionBar aria-label="x" sticky />)
    const root = container.firstChild as HTMLElement
    expect(root.className).toContain('sticky')
    expect(root.className).toContain('top-0')
  })

  it('without sticky, is not sticky', () => {
    const { container } = render(<ActionBar aria-label="x" />)
    const root = container.firstChild as HTMLElement
    expect(root.className).not.toContain('sticky')
  })

  it('glass prop applies glass-toolbar class', () => {
    const { container } = render(<ActionBar aria-label="x" glass />)
    const root = container.firstChild as HTMLElement
    expect(root.className).toContain('glass-toolbar')
  })

  it('right slot items use charcoal Button variant (no brass)', () => {
    render(
      <ActionBar
        aria-label="x"
        right={<Button>Save</Button>}
      />
    )
    const btn = screen.getByRole('button', { name: 'Save' })
    expect(btn.className).not.toMatch(/bg-brand/)
  })

  it('accepts className override', () => {
    const { container } = render(<ActionBar aria-label="x" className="my-bar" />)
    expect(container.firstChild).toHaveClass('my-bar')
  })
})
