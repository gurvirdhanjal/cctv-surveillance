import { Helmet } from 'react-helmet-async'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { HealthResponse, ReadinessResponse, StateSnapshot } from '@/shared/api/types'

function StatusBadge({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded text-[12px] font-medium ${
        ok ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
      }`}
    >
      {ok ? 'OK' : 'FAIL'}
    </span>
  )
}

export function AdminDashboardPage() {
  const { data: health } = useQuery<HealthResponse>({
    queryKey: ['admin', 'health'],
    queryFn: () => api.get('/api/health'),
  })
  const { data: ready } = useQuery<ReadinessResponse>({
    queryKey: ['admin', 'ready'],
    queryFn: () => api.get('/api/ready'),
  })
  const { data: snapshot } = useQuery<StateSnapshot>({
    queryKey: ['admin', 'snapshot'],
    queryFn: () => api.get('/api/state/snapshot'),
  })

  const onlineCameras = (snapshot?.cameras ?? []).filter((c) => c.is_active).length
  const totalCameras = snapshot?.cameras?.length ?? 0

  return (
    <>
      <Helmet title="System Dashboard — Admin" />
      <div className="p-6 max-w-4xl">
        <h1 className="text-[24px] font-semibold text-text-primary mb-6">System Dashboard</h1>

        <section aria-label="System health" className="mb-8">
          <h2 className="text-[13px] font-semibold uppercase tracking-wider text-text-tertiary mb-3">
            Health
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div className="bg-surface-elevated rounded border border-border-subtle p-4">
              <p className="text-[12px] text-text-tertiary mb-2">API Status</p>
              <StatusBadge ok={health?.status === 'ok'} />
            </div>
            <div className="bg-surface-elevated rounded border border-border-subtle p-4">
              <p className="text-[12px] text-text-tertiary mb-2">Database</p>
              <StatusBadge ok={ready?.db === 'ok'} />
            </div>
            <div className="bg-surface-elevated rounded border border-border-subtle p-4">
              <p className="text-[12px] text-text-tertiary mb-2">Redis</p>
              <StatusBadge ok={ready?.redis === 'ok'} />
            </div>
            <div className="bg-surface-elevated rounded border border-border-subtle p-4">
              <p className="text-[12px] text-text-tertiary mb-2">Version</p>
              <p className="text-[14px] font-mono text-text-primary">{health?.version ?? '—'}</p>
            </div>
          </div>
        </section>

        <section aria-label="System metrics">
          <h2 className="text-[13px] font-semibold uppercase tracking-wider text-text-tertiary mb-3">
            Metrics
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div className="bg-surface-elevated rounded border border-border-subtle p-4">
              <p className="text-[12px] text-text-tertiary mb-1">Head Count</p>
              <p className="text-[28px] font-bold text-text-primary tabular-nums">
                {snapshot?.head_count?.plant_total ?? '—'}
              </p>
            </div>
            <div className="bg-surface-elevated rounded border border-border-subtle p-4">
              <p className="text-[12px] text-text-tertiary mb-1">Cameras Online</p>
              <p className="text-[28px] font-bold text-text-primary tabular-nums">
                {totalCameras > 0 ? `${onlineCameras}/${totalCameras}` : '—'}
              </p>
            </div>
            <div className="bg-surface-elevated rounded border border-border-subtle p-4">
              <p className="text-[12px] text-text-tertiary mb-1">Active Alerts</p>
              <p className="text-[28px] font-bold text-text-primary tabular-nums">
                {snapshot?.active_alerts?.length ?? '—'}
              </p>
            </div>
          </div>
        </section>
      </div>
    </>
  )
}
