import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { AlertCountByType } from '@/shared/api/types'

vi.mock('@/shared/charts/EChartsWrapper', () => ({
  EChartsWrapper: ({ option }: { option: { series?: Array<{ type?: string }> } }) => (
    <div data-testid="echarts-wrapper" data-series-type={option?.series?.[0]?.type} />
  ),
  useChartTheme: () => ({ textColor: '#e2e8f0', mutedColor: '#64748b', borderColor: '#1e293b', backgroundColor: '#1a2234' }),
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
  it('renders ECharts bar chart', () => {
    render(<AlertVolumeChart data={sampleData} />)
    expect(screen.getByTestId('echarts-wrapper')).toBeInTheDocument()
    expect(screen.getByTestId('echarts-wrapper').getAttribute('data-series-type')).toBe('bar')
  })

  it('renders loading skeleton when loading', () => {
    render(<AlertVolumeChart data={[]} loading />)
    expect(screen.getByRole('status', { name: 'Loading chart' })).toBeInTheDocument()
  })

  it('has accessible label', () => {
    render(<AlertVolumeChart data={sampleData} />)
    expect(screen.getByLabelText('Alert volume by type')).toBeInTheDocument()
  })

  it('does not render recharts-wrapper element', () => {
    const { container } = render(<AlertVolumeChart data={sampleData} />)
    expect(container.querySelector('.recharts-wrapper')).toBeNull()
  })
})
