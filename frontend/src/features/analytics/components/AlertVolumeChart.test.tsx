import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { AlertCountByType } from '@/shared/api/types'

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-container">{children}</div>
  ),
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  Bar: () => null,
  Cell: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
}))

const { AlertVolumeChart } = await import('./AlertVolumeChart')

const sampleData: AlertCountByType[] = [
  { alert_type: 'INTRUSION', count: 12 },
  { alert_type: 'UNKNOWN_PERSON', count: 8 },
  { alert_type: 'LOITERING', count: 5 },
  { alert_type: 'VIOLENCE', count: 3 },
  { alert_type: 'PPE_VIOLATION', count: 2 },
  { alert_type: 'SYSTEM_CRITICAL', count: 1 },
]

describe('AlertVolumeChart', () => {
  it('renders bar chart', () => {
    render(<AlertVolumeChart data={sampleData} />)
    expect(screen.getByTestId('bar-chart')).toBeInTheDocument()
  })

  it('renders loading skeleton when loading', () => {
    render(<AlertVolumeChart data={[]} loading />)
    expect(screen.getByRole('status', { name: 'Loading chart' })).toBeInTheDocument()
  })

  it('has accessible label', () => {
    render(<AlertVolumeChart data={sampleData} />)
    expect(screen.getByLabelText('Alert volume by type')).toBeInTheDocument()
  })
})
