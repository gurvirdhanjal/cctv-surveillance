import { EChartsWrapper, useChartTheme } from '@/shared/charts/EChartsWrapper'
import type { AlertCountByType } from '@/shared/api/types'

const ALERT_COLORS: Record<string, string> = {
  INTRUSION: '#dc2626',
  VIOLENCE: '#9333ea',
  UNKNOWN_PERSON: '#d97706',
  LOITERING: '#2563eb',
  PPE_VIOLATION: '#16a34a',
  SYSTEM_CRITICAL: '#6b7280',
}

interface AlertVolumeChartProps {
  data: AlertCountByType[]
  loading?: boolean
}

export function AlertVolumeChart({ data, loading = false }: AlertVolumeChartProps) {
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

  const top5 = [...data].sort((a, b) => b.count - a.count).slice(0, 5)

  const option = {
    grid: { top: 8, right: 16, bottom: 28, left: 8, containLabel: true },
    tooltip: { trigger: 'axis' as const, textStyle: { fontSize: 12 } },
    xAxis: {
      type: 'category' as const,
      data: top5.map((d) => d.alert_type.replace(/_/g, ' ')),
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: theme.mutedColor, fontSize: 11 },
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
        type: 'bar' as const,
        data: top5.map((d) => ({
          value: d.count,
          itemStyle: { color: ALERT_COLORS[d.alert_type] ?? '#2b6cb0', borderRadius: [3, 3, 0, 0] },
        })),
        name: 'Count',
        barMaxWidth: 40,
      },
    ],
  }

  return (
    <div aria-label="Alert volume by type" className="h-48 w-full">
      <EChartsWrapper option={option} style={{ height: '100%', width: '100%' }} />
    </div>
  )
}
