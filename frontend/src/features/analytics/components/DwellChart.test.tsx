import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
}))

const { DwellChart } = await import('./DwellChart')

describe('DwellChart', () => {
  it('renders bar chart', () => {
    render(<DwellChart data={[{ zone_name: 'Entrance', dwell_minutes: 20 }]} />)
    expect(screen.getByTestId('bar-chart')).toBeInTheDocument()
  })

  it('shows loading skeleton', () => {
    render(<DwellChart data={[]} loading />)
    expect(screen.getByRole('status', { name: 'Loading dwell chart' })).toBeInTheDocument()
  })

  it('has accessible label', () => {
    render(<DwellChart data={[]} />)
    expect(screen.getByLabelText('Zone dwell times')).toBeInTheDocument()
  })
})
