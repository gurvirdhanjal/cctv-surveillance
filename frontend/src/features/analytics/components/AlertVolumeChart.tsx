import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from 'recharts'
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

  return (
    <div aria-label="Alert volume by type" className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={top5} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-default)" vertical={false} />
          <XAxis
            dataKey="alert_type"
            tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
            tickLine={false}
            tickFormatter={(v: string) => v.replace(/_/g, ' ')}
          />
          <YAxis
            tick={{ fontSize: 12, fill: 'var(--text-muted)' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip contentStyle={{ fontSize: 12 }} />
          <Bar dataKey="count" name="Count" radius={[3, 3, 0, 0]}>
            {top5.map((entry) => (
              <Cell key={entry.alert_type} fill={ALERT_COLORS[entry.alert_type] ?? '#2b6cb0'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
