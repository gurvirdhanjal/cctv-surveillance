import { Helmet } from 'react-helmet-async'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { ZoneResponse } from '@/shared/api/types'
import { HeatmapOverlay } from './components/HeatmapOverlay'

type TimeWindow = 'today' | 'week' | 'month'

export function HeatmapPage() {
  const [timeWindow, setTimeWindow] = useState<TimeWindow>('today')

  const { data: zones = [] } = useQuery({
    queryKey: ['zones'],
    queryFn: () => api.get<ZoneResponse[]>('/api/zones'),
    staleTime: 300_000,
  })

  return (
    <>
      <Helmet title="Heatmap" />
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-[20px] font-semibold text-text-primary">Dwell Heatmap</h1>
          <div className="flex gap-2" aria-label="Time window">
            {(['today', 'week', 'month'] as TimeWindow[]).map((w) => (
              <button
                key={w}
                aria-pressed={timeWindow === w}
                onClick={() => setTimeWindow(w)}
                className={[
                  'rounded-md px-3 py-1.5 text-[12px] capitalize transition-colors',
                  timeWindow === w
                    ? 'bg-action-700 text-white'
                    : 'border border text-text-secondary hover:bg-surface-sunken',
                ].join(' ')}
              >
                {w}
              </button>
            ))}
          </div>
        </div>

        <div
          className="relative overflow-hidden rounded-lg border border bg-surface-sunken"
          style={{ height: 400 }}
        >
          {zones.length > 0 ? (
            <HeatmapOverlay zones={zones} dwellData={[]} imageWidth={800} imageHeight={400} />
          ) : (
            <div className="flex h-full items-center justify-center text-[14px] text-text-muted">
              No zones configured — add zones in Admin &gt; Zones to see heatmap data.
            </div>
          )}
        </div>
      </div>
    </>
  )
}
