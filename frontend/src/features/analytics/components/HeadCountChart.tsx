import { EChartsWrapper, useChartTheme } from '@/shared/charts/EChartsWrapper'
import type { HeadCountPoint } from '@/shared/api/types'

interface HeadCountChartProps {
  data: HeadCountPoint[]
  loading?: boolean
}

export function HeadCountChart({ data, loading = false }: HeadCountChartProps) {
  const theme = useChartTheme()

  if (loading) {
    return (
      <div
        role="status"
        aria-label="Loading chart"
        className="h-48 animate-pulse rounded bg-surface-sunken"
      />
    )
  }

  const option = {
    grid: { top: 8, right: 16, bottom: 28, left: 8, containLabel: true },
    tooltip: { trigger: 'axis' as const, textStyle: { fontSize: 12 } },
    legend: { data: ['Peak', 'Avg'], bottom: 0, textStyle: { color: theme.mutedColor, fontSize: 11 } },
    xAxis: {
      type: 'category' as const,
      data: data.map((d) => d.date),
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: theme.mutedColor, fontSize: 12 },
    },
    yAxis: {
      type: 'value' as const,
      axisTick: { show: false },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: theme.borderColor } },
      axisLabel: { color: theme.mutedColor, fontSize: 12 },
    },
    series: [
      {
        type: 'line' as const,
        name: 'Peak',
        data: data.map((d) => d.peak),
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#2b6cb0', width: 2 },
        itemStyle: { color: '#2b6cb0' },
      },
      {
        type: 'line' as const,
        name: 'Avg',
        data: data.map((d) => d.avg),
        smooth: true,
        symbol: 'none',
        lineStyle: { color: '#7eb0ff', width: 2, type: 'dashed' as const },
        itemStyle: { color: '#7eb0ff' },
      },
    ],
  }

  return (
    <div aria-label="Head count over 7 days" className="h-48 w-full">
      <EChartsWrapper option={option} style={{ height: '100%', width: '100%' }} />
    </div>
  )
}
