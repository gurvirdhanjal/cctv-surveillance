import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { HeadCountPoint } from '@/shared/api/types'

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-container">{children}</div>
  ),
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
}))

const { HeadCountChart } = await import('./HeadCountChart')

const sampleData: HeadCountPoint[] = [
  { date: '2026-06-17', peak: 30, avg: 22 },
  { date: '2026-06-18', peak: 35, avg: 27 },
]

describe('HeadCountChart', () => {
  it('renders line chart with data', () => {
    render(<HeadCountChart data={sampleData} />)
    expect(screen.getByTestId('line-chart')).toBeInTheDocument()
  })

  it('renders loading skeleton when loading', () => {
    render(<HeadCountChart data={[]} loading />)
    expect(screen.getByRole('status', { name: 'Loading chart' })).toBeInTheDocument()
  })

  it('has accessible container label', () => {
    render(<HeadCountChart data={sampleData} />)
    expect(screen.getByLabelText('Head count over 7 days')).toBeInTheDocument()
  })
})
