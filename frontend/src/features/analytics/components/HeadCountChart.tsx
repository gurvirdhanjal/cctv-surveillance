import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'
import type { HeadCountPoint } from '@/shared/api/types'

interface HeadCountChartProps {
  data: HeadCountPoint[]
  loading?: boolean
}

export function HeadCountChart({ data, loading = false }: HeadCountChartProps) {
  if (loading) {
    return (
      <div
        role="status"
        aria-label="Loading chart"
        className="h-48 animate-pulse rounded bg-surface-sunken"
      />
    )
  }

  return (
    <div aria-label="Head count over 7 days" className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-default)" />
          <XAxis dataKey="date" tick={{ fontSize: 12, fill: 'var(--text-muted)' }} tickLine={false} />
          <YAxis tick={{ fontSize: 12, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
          <Tooltip contentStyle={{ fontSize: 12 }} />
          <Line
            type="monotone"
            dataKey="peak"
            stroke="#2b6cb0"
            strokeWidth={2}
            dot={false}
            name="Peak"
          />
          <Line
            type="monotone"
            dataKey="avg"
            stroke="#7eb0ff"
            strokeWidth={2}
            dot={false}
            name="Avg"
            strokeDasharray="4 2"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
