import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('@/shared/charts/EChartsWrapper', () => ({
  EChartsWrapper: ({ option }: { option: { series?: Array<{ type?: string }> } }) => (
    <div data-testid="echarts-wrapper" data-series-type={option?.series?.[0]?.type} />
  ),
  useChartTheme: () => ({ textColor: '#e2e8f0', mutedColor: '#64748b', borderColor: '#1e293b', backgroundColor: '#1a2234' }),
}))

const { DwellChart } = await import('./DwellChart')

describe('DwellChart', () => {
  it('renders ECharts bar chart', () => {
    render(<DwellChart data={[{ zone_name: 'Entrance', dwell_minutes: 20 }]} />)
    expect(screen.getByTestId('echarts-wrapper')).toBeInTheDocument()
    expect(screen.getByTestId('echarts-wrapper').getAttribute('data-series-type')).toBe('bar')
  })

  it('shows loading skeleton', () => {
    render(<DwellChart data={[]} loading />)
    expect(screen.getByRole('status', { name: 'Loading dwell chart' })).toBeInTheDocument()
  })

  it('has accessible label', () => {
    render(<DwellChart data={[]} />)
    expect(screen.getByLabelText('Zone dwell times')).toBeInTheDocument()
  })

  it('does not render recharts-wrapper element', () => {
    const { container } = render(<DwellChart data={[]} />)
    expect(container.querySelector('.recharts-wrapper')).toBeNull()
  })
})
