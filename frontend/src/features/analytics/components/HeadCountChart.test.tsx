import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { HeadCountPoint } from '@/shared/api/types'

vi.mock('@/shared/charts/EChartsWrapper', () => ({
  EChartsWrapper: ({ option }: { option: { series?: Array<{ type?: string }> } }) => (
    <div data-testid="echarts-wrapper" data-series-type={option?.series?.[0]?.type} />
  ),
  useChartTheme: () => ({ textColor: '#e2e8f0', mutedColor: '#64748b', borderColor: '#1e293b', backgroundColor: '#1a2234' }),
}))

const { HeadCountChart } = await import('./HeadCountChart')

const sampleData: HeadCountPoint[] = [
  { date: '2026-06-17', peak: 30, avg: 22 },
  { date: '2026-06-18', peak: 35, avg: 27 },
]

describe('HeadCountChart', () => {
  it('renders ECharts line chart with data', () => {
    render(<HeadCountChart data={sampleData} />)
    expect(screen.getByTestId('echarts-wrapper')).toBeInTheDocument()
    expect(screen.getByTestId('echarts-wrapper').getAttribute('data-series-type')).toBe('line')
  })

  it('renders loading skeleton when loading', () => {
    render(<HeadCountChart data={[]} loading />)
    expect(screen.getByRole('status', { name: 'Loading chart' })).toBeInTheDocument()
  })

  it('has accessible container label', () => {
    render(<HeadCountChart data={sampleData} />)
    expect(screen.getByLabelText('Head count over 7 days')).toBeInTheDocument()
  })

  it('does not render recharts-wrapper element', () => {
    const { container } = render(<HeadCountChart data={sampleData} />)
    expect(container.querySelector('.recharts-wrapper')).toBeNull()
  })
})
