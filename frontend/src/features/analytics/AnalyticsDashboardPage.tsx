import { Helmet } from 'react-helmet-async'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/shared/api/client'
import type {
  AnalyticsKpi,
  HeadCountPoint,
  AlertCountByType,
  AlertResponse,
  CameraResponse,
} from '@/shared/api/types'
import { KpiCard } from './components/KpiCard'
import { HeadCountChart } from './components/HeadCountChart'
import { AlertVolumeChart } from './components/AlertVolumeChart'

export function AnalyticsDashboardPage() {
  const { data: kpi, isLoading: kpiLoading, isError: kpiError } = useQuery({
    queryKey: ['analytics-kpi'],
    queryFn: () => api.get<AnalyticsKpi>('/api/analytics/kpi'),
    staleTime: 60_000,
  })

  const { data: headCountSeries, isLoading: hcLoading } = useQuery({
    queryKey: ['head-count-series'],
    queryFn: () => api.get<HeadCountPoint[]>('/api/analytics/head-count?days=7'),
    staleTime: 300_000,
  })

  const { data: alertsData } = useQuery({
    queryKey: ['alerts-for-chart'],
    queryFn: () => api.get<{ items: AlertResponse[] }>('/api/alerts?limit=200'),
    staleTime: 60_000,
  })

  const { data: cameras } = useQuery({
    queryKey: ['cameras'],
    queryFn: () => api.get<CameraResponse[]>('/api/cameras'),
    staleTime: 300_000,
  })

  const alertCountByType: AlertCountByType[] = alertsData
    ? (Object.entries(
        alertsData.items.reduce<Record<string, number>>((acc, a) => {
          acc[a.alert_type] = (acc[a.alert_type] ?? 0) + 1
          return acc
        }, {}),
      ).map(([alert_type, count]) => ({
        alert_type: alert_type as AlertCountByType['alert_type'],
        count,
      })) as AlertCountByType[])
    : []

  const cameraUptime = cameras
    ? Math.round((cameras.filter((c) => c.is_active).length / Math.max(1, cameras.length)) * 100)
    : null

  return (
    <>
      <Helmet title="Dashboard" />
      <div className="space-y-6">
        <h1 className="text-[20px] font-semibold text-text-primary">Analytics Dashboard</h1>

        <section aria-label="Key metrics" className="grid grid-cols-4 gap-4">
          <KpiCard
            label="Head Count Peak"
            value={kpi?.head_count_peak ?? null}
            loading={kpiLoading}
            error={kpiError}
          />
          <KpiCard
            label="Avg Dwell"
            value={kpi?.avg_dwell_minutes != null ? kpi.avg_dwell_minutes.toFixed(1) : null}
            unit="min"
            loading={kpiLoading}
            error={kpiError}
          />
          <KpiCard
            label="Unknown Person Events"
            value={kpi?.unknown_person_events ?? null}
            loading={kpiLoading}
            error={kpiError}
          />
          <KpiCard label="Camera Uptime" value={cameraUptime} unit="%" />
        </section>

        <section aria-label="Charts" className="grid grid-cols-2 gap-6">
          <div>
            <h2 className="mb-2 text-[14px] font-medium text-text-secondary">
              Head Count — 7 days
            </h2>
            <HeadCountChart data={headCountSeries ?? []} loading={hcLoading} />
          </div>
          <div>
            <h2 className="mb-2 text-[14px] font-medium text-text-secondary">
              Alert Volume by Type
            </h2>
            <AlertVolumeChart data={alertCountByType} />
          </div>
        </section>

        <section aria-label="Quick actions" className="flex flex-wrap gap-3">
          <Link
            to="/analytics/timeline"
            className="rounded-md border border px-4 py-2 text-[13px] text-text-secondary transition-colors hover:bg-surface-sunken"
          >
            Open Timeline
          </Link>
          <Link
            to="/analytics/heatmap"
            className="rounded-md border border px-4 py-2 text-[13px] text-text-secondary transition-colors hover:bg-surface-sunken"
          >
            View Heatmap
          </Link>
          <Link
            to="/forensic"
            className="rounded-md border border px-4 py-2 text-[13px] text-text-secondary transition-colors hover:bg-surface-sunken"
          >
            Forensic Search
          </Link>
        </section>
      </div>
    </>
  )
}
