import { EChartsWrapper, useChartTheme } from '@/shared/charts/EChartsWrapper'

interface DwellEntry {
  zone_name: string
  dwell_minutes: number
}

interface DwellChartProps {
  data: DwellEntry[]
  loading?: boolean
}

export function DwellChart({ data, loading = false }: DwellChartProps) {
  const theme = useChartTheme()

  if (loading) {
    return (
      <div
        role="status"
        aria-label="Loading dwell chart"
        className="h-40 animate-pulse rounded bg-surface-sunken"
      />
    )
  }

  const option = {
    grid: { top: 8, right: 24, bottom: 8, left: 60, containLabel: false },
    tooltip: { trigger: 'axis' as const, textStyle: { fontSize: 12 }, formatter: '{b}: {c} min' },
    xAxis: {
      type: 'value' as const,
      axisTick: { show: false },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: theme.borderColor } },
      axisLabel: { color: theme.mutedColor, fontSize: 11, formatter: '{value} min' },
    },
    yAxis: {
      type: 'category' as const,
      data: data.map((d) => d.zone_name),
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: theme.textColor, fontSize: 12 },
    },
    series: [
      {
        type: 'bar' as const,
        data: data.map((d) => d.dwell_minutes),
        name: 'Dwell (min)',
        barMaxWidth: 32,
        itemStyle: { color: '#2b6cb0', borderRadius: [0, 3, 3, 0] },
      },
    ],
  }

  return (
    <div aria-label="Zone dwell times" className="h-40 w-full">
      <EChartsWrapper option={option} style={{ height: '100%', width: '100%' }} />
    </div>
  )
}
