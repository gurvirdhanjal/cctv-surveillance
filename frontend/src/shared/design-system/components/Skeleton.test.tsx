import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import {
  Skeleton, SkeletonText, SkeletonTable, SkeletonKpiGrid,
  SkeletonKpiCard, SkeletonCameraCard, SkeletonTableRow, SkeletonAvatar,
  SkeletonTimeline, SkeletonCameraTree, SkeletonChart,
} from './Skeleton'

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

// §L spec composites
describe('SkeletonKpiCard (§L)', () => {
  it('renders without error', () => {
    expect(() => render(<SkeletonKpiCard />)).not.toThrow()
  })

  it('uses animate-pulse shimmer', () => {
    const { container } = render(<SkeletonKpiCard />)
    expect(container.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('is aria-hidden', () => {
    const { container } = render(<SkeletonKpiCard />)
    expect(container.firstElementChild?.getAttribute('aria-hidden')).toBe('true')
  })
})

describe('SkeletonCameraCard (§L)', () => {
  it('renders without error', () => {
    expect(() => render(<SkeletonCameraCard />)).not.toThrow()
  })

  it('uses animate-pulse shimmer', () => {
    const { container } = render(<SkeletonCameraCard />)
    expect(container.querySelector('.animate-pulse')).toBeTruthy()
  })
})

describe('SkeletonTableRow (§L)', () => {
  it('renders one bar per column in columnWidths', () => {
    const { container } = render(<SkeletonTableRow columnWidths={[80, 200, 64]} />)
    const bars = container.querySelectorAll('.animate-pulse')
    expect(bars.length).toBe(3)
  })

  it('applies hinted widths as inline styles', () => {
    const { container } = render(<SkeletonTableRow columnWidths={[120, 240]} />)
    const bars = Array.from(container.querySelectorAll('.animate-pulse')) as HTMLElement[]
    expect(bars[0].style.width).toBe('120px')
    expect(bars[1].style.width).toBe('240px')
  })

  it('renders a default row when no columnWidths given', () => {
    expect(() => render(<SkeletonTableRow />)).not.toThrow()
  })
})

describe('SkeletonAvatar (§L supplement)', () => {
  it('renders without error', () => {
    expect(() => render(<SkeletonAvatar />)).not.toThrow()
  })

  it('is circular', () => {
    const { container } = render(<SkeletonAvatar />)
    expect((container.firstElementChild as HTMLElement).className).toContain('rounded-full')
  })
})

describe('SkeletonTimeline (§I)', () => {
  it('renders with 120px height', () => {
    const { container } = render(<SkeletonTimeline />)
    const el = container.firstElementChild as HTMLElement
    expect(el.style.height).toBe('120px')
  })

  it('renders 8 mark skeletons', () => {
    const { container } = render(<SkeletonTimeline />)
    // base bar + 8 marks = 9 animate-pulse children
    const pulses = container.querySelectorAll('.animate-pulse')
    expect(pulses.length).toBe(9)
  })

  it('is aria-hidden', () => {
    const { container } = render(<SkeletonTimeline />)
    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true')
  })
})

describe('SkeletonCameraTree (§Q)', () => {
  it('renders without error', () => {
    expect(() => render(<SkeletonCameraTree />)).not.toThrow()
  })

  it('renders group header skeletons', () => {
    const { container } = render(<SkeletonCameraTree />)
    // 3 groups each with a header → at least 3 aria-hidden els
    const hidden = container.querySelectorAll('[aria-hidden="true"]')
    expect(hidden.length).toBeGreaterThanOrEqual(3)
  })
})

describe('SkeletonChart (§V.2)', () => {
  it('renders with status role and accessible label', () => {
    const { getByRole } = render(<SkeletonChart />)
    expect(getByRole('status', { name: 'Loading chart' })).toBeInTheDocument()
  })

  it('applies default height of 192px', () => {
    const { container } = render(<SkeletonChart />)
    const el = container.firstElementChild as HTMLElement
    expect(el.style.height).toBe('192px')
  })

  it('accepts custom style override', () => {
    const { container } = render(<SkeletonChart style={{ height: 120 }} />)
    const el = container.firstElementChild as HTMLElement
    expect(el.style.height).toBe('120px')
  })
})
