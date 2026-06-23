import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'

interface DwellEntry {
  zone_name: string
  dwell_minutes: number
}

interface DwellChartProps {
  data: DwellEntry[]
  loading?: boolean
}

export function DwellChart({ data, loading = false }: DwellChartProps) {
  if (loading) {
    return (
      <div
        role="status"
        aria-label="Loading dwell chart"
        className="h-40 animate-pulse rounded bg-surface-sunken"
      />
    )
  }

  return (
    <div aria-label="Zone dwell times" className="h-40 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 24, bottom: 4, left: 60 }}
        >
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--border-default)" />
          <XAxis
            type="number"
            unit=" min"
            tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
            tickLine={false}
          />
          <YAxis
            dataKey="zone_name"
            type="category"
            tick={{ fontSize: 12, fill: 'var(--text-primary)' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip contentStyle={{ fontSize: 12 }} />
          <Bar dataKey="dwell_minutes" fill="#2b6cb0" radius={[0, 3, 3, 0]} name="Dwell (min)" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
