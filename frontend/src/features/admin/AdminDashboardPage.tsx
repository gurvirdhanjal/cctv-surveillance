import { Helmet } from 'react-helmet-async'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { HealthResponse, ReadinessResponse, StateSnapshot } from '@/shared/api/types'

type ServiceStatus = 'ok' | 'fail' | 'loading'

function StatusBadge({ status }: { status: ServiceStatus }) {
  if (status === 'loading') {
    return <span className="inline-block h-5 w-12 animate-pulse rounded bg-surface-sunken" />
  }
  return (
    <span
      className={`inline-block rounded px-2 py-0.5 text-[12px] font-semibold ${
        status === 'ok' ? 'bg-success/10 text-success' : 'bg-error/10 text-error'
      }`}
    >
      {status === 'ok' ? 'OK' : 'FAIL'}
    </span>
  )
}

export function AdminDashboardPage() {
  const { data: health, isPending: healthPending } = useQuery<HealthResponse>({
    queryKey: ['admin', 'health'],
    queryFn: () => api.get('/api/health'),
    refetchInterval: 30_000,
  })

  // /api/ready returns 503 when services are down; we still want to show which ones
  // failed. Primary path uses api.get; if that throws (503) we fall back to raw fetch
  // to extract the response body.
  const { data: ready, isPending: readyPending } = useQuery<ReadinessResponse | null>({
    queryKey: ['admin', 'ready'],
    queryFn: async () => {
      try {
        return await api.get<ReadinessResponse>('/api/ready')
      } catch {
        try {
          const r = await fetch('/api/ready')
          return (await r.json()) as ReadinessResponse
        } catch {
          return null
        }
      }
    },
    refetchInterval: 30_000,
  })

  const { data: snapshot } = useQuery<StateSnapshot>({
    queryKey: ['admin', 'snapshot'],
    queryFn: () => api.get('/api/state/snapshot'),
    refetchInterval: 10_000,
  })

  const activeCameras = (snapshot?.cameras ?? []).filter((c) => c.is_active).length
  const totalCameras = snapshot?.cameras?.length ?? 0

  const apiStatus: ServiceStatus = healthPending ? 'loading' : health?.status === 'ok' ? 'ok' : 'fail'
  const dbStatus: ServiceStatus = readyPending ? 'loading' : ready?.db === 'ok' ? 'ok' : 'fail'
  const redisStatus: ServiceStatus = readyPending ? 'loading' : ready?.redis === 'ok' ? 'ok' : 'fail'

  return (
    <>
      <Helmet title="System Dashboard — Admin" />
      <div className="p-6 max-w-4xl">
        <h1 className="mb-6 text-[24px] font-semibold text-text-primary">System Dashboard</h1>

        <section aria-label="System health" className="mb-8">
          <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-text-muted">
            Health
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="rounded border border-border bg-surface-raised p-4">
              <p className="mb-2 text-[12px] text-text-muted">API</p>
              <StatusBadge status={apiStatus} />
            </div>
            <div className="rounded border border-border bg-surface-raised p-4">
              <p className="mb-2 text-[12px] text-text-muted">Database</p>
              <StatusBadge status={dbStatus} />
            </div>
            <div className="rounded border border-border bg-surface-raised p-4">
              <p className="mb-2 text-[12px] text-text-muted">Redis</p>
              <StatusBadge status={redisStatus} />
            </div>
            <div className="rounded border border-border bg-surface-raised p-4">
              <p className="mb-2 text-[12px] text-text-muted">Version</p>
              <p className="font-mono text-[14px] text-text-primary">
                {healthPending ? (
                  <span className="inline-block h-4 w-12 animate-pulse rounded bg-surface-sunken" />
                ) : (
                  (health?.version ?? '—')
                )}
              </p>
            </div>
          </div>
        </section>

        <section aria-label="System metrics">
          <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-text-muted">
            Metrics
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div className="rounded border border-border bg-surface-raised p-4">
              <p className="mb-1 text-[12px] text-text-muted">Head Count</p>
              <p className="tabular-nums text-[28px] font-bold text-text-primary">
                {snapshot?.head_count?.plant_total ?? '—'}
              </p>
            </div>
            <div className="rounded border border-border bg-surface-raised p-4">
              <p className="mb-1 text-[12px] text-text-muted">Cameras Online</p>
              <p className="tabular-nums text-[28px] font-bold text-text-primary">
                {totalCameras > 0 ? `${activeCameras}/${totalCameras}` : '—'}
              </p>
            </div>
            <div className="rounded border border-border bg-surface-raised p-4">
              <p className="mb-1 text-[12px] text-text-muted">Active Alerts</p>
              <p className="tabular-nums text-[28px] font-bold text-text-primary">
                {snapshot?.active_alerts?.length ?? '—'}
              </p>
            </div>
          </div>
        </section>
      </div>
    </>
  )
}
