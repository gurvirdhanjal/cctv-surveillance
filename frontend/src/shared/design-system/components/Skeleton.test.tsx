import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Skeleton, SkeletonText, SkeletonTable, SkeletonKpiGrid } from './Skeleton'

describe('Skeleton', () => {
  it('renders with pulse and base classes', () => {
    const { container } = render(<Skeleton />)
    const el = container.firstChild as HTMLElement
    expect(el).toHaveClass('animate-pulse')
    expect(el).toHaveClass('rounded')
    expect(el).toHaveClass('bg-surface-raised')
  })

  it('is hidden from assistive technology', () => {
    const { container } = render(<Skeleton />)
    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true')
  })

  it('accepts className override', () => {
    const { container } = render(<Skeleton className="h-4 w-32" />)
    expect(container.firstChild).toHaveClass('h-4', 'w-32')
  })
})

describe('SkeletonText', () => {
  it('renders multiple skeleton lines', () => {
    const { container } = render(<SkeletonText lines={3} />)
    const lines = container.querySelectorAll('[aria-hidden="true"]')
    expect(lines.length).toBeGreaterThanOrEqual(3)
  })
})

describe('SkeletonTable', () => {
  it('renders requested row count', () => {
    const { container } = render(<SkeletonTable rows={5} />)
    const rows = container.querySelectorAll('[aria-hidden="true"]')
    expect(rows.length).toBeGreaterThanOrEqual(5)
  })
})

describe('SkeletonKpiGrid', () => {
  it('renders 4 KPI cards by default', () => {
    const { container } = render(<SkeletonKpiGrid />)
    const cards = container.querySelectorAll('[aria-hidden="true"]')
    expect(cards.length).toBeGreaterThanOrEqual(4)
  })
})
