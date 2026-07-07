import { useMemo } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  CheckCircle2,
  XCircle,
  Camera,
  Users,
  Bell,
  Zap,
  ShieldAlert,
  Clock,
  AlertTriangle,
  HardDrive,
} from 'lucide-react'
import { api } from '@/shared/api/client'
import type { HealthResponse, ReadinessResponse, StateSnapshot, AlertType } from '@/shared/api/types'
import { PageHeader } from '@/shared/design-system/components/PageHeader'

type ServiceStatus = 'ok' | 'fail' | 'loading'

function StatusBadge({ status }: { status: ServiceStatus }) {
  if (status === 'loading') {
    return <span className="inline-block h-5 w-10 animate-pulse rounded-full bg-surface-sunken" />
  }
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-semibold ${
        status === 'ok' ? 'bg-success/10 text-success' : 'bg-error/10 text-error'
      }`}
    >
      {status === 'ok' ? 'OK' : 'FAIL'}
    </span>
  )
}

function ServiceRow({ name, status }: { name: string; status: ServiceStatus }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-border bg-surface-base px-4 py-3 shadow-1 hover:shadow-2 transition-shadow duration-fast cursor-default">
      <div className="flex items-center gap-3">
        {status === 'loading' ? (
          <span className="h-4 w-4 animate-pulse rounded-full bg-surface-sunken" />
        ) : status === 'ok' ? (
          <CheckCircle2 className="h-4 w-4 shrink-0 text-success" aria-hidden="true" />
        ) : (
          <XCircle className="h-4 w-4 shrink-0 text-error" aria-hidden="true" />
        )}
        <p className="text-[13px] font-medium text-text-primary">{name}</p>
      </div>
      <StatusBadge status={status} />
    </div>
  )
}

interface KpiCardProps {
  label: string
  value: string | number
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' | 'false' }>
  to: string
  accent: string
  isPending?: boolean
}

function KpiCard({ label, value, icon: Icon, to, accent, isPending = false }: KpiCardProps) {
  return (
    <div className="rounded-xl border border-border bg-surface-base p-6 shadow-1 hover:shadow-2 transition-shadow duration-fast cursor-default">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            {label}
          </p>
          <p className="mt-2 tabular-nums text-[30px] font-bold leading-none text-text-primary">
            {isPending ? (
              <span className="inline-block h-8 w-14 animate-pulse rounded-lg bg-surface-sunken align-middle" />
            ) : (
              value
            )}
          </p>
        </div>
        <Link
          to={to}
          className={`shrink-0 rounded-xl p-3 transition-opacity hover:opacity-80 ${accent}`}
          tabIndex={-1}
          aria-hidden="true"
        >
          <Icon className="h-5 w-5" aria-hidden="true" />
        </Link>
      </div>
    </div>
  )
}

const ALERT_TYPE_META: Record<AlertType, { label: string; icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' | 'false' }>; accent: string }> = {
  INTRUSION: { label: 'Intrusion', icon: ShieldAlert, accent: 'text-error' },
  LOITERING: { label: 'Loitering', icon: Clock, accent: 'text-warning' },
  UNKNOWN_PERSON: { label: 'Unknown', icon: Users, accent: 'text-info' },
  VIOLENCE: { label: 'Violence', icon: AlertTriangle, accent: 'text-error' },
  PPE_VIOLATION: { label: 'PPE', icon: HardDrive, accent: 'text-warning' },
  SYSTEM_CRITICAL: { label: 'System', icon: Zap, accent: 'text-error' },
}

const ALERT_TYPE_ORDER: AlertType[] = [
  'INTRUSION',
  'VIOLENCE',
  'UNKNOWN_PERSON',
  'LOITERING',
  'PPE_VIOLATION',
]

export function AdminDashboardPage() {
  const { data: health, isPending: healthPending } = useQuery<HealthResponse>({
    queryKey: ['admin', 'health'],
    queryFn: () => api.get('/api/health'),
    refetchInterval: 30_000,
  })

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
  const offlineCameras = totalCameras - activeCameras
  const needsCalibration = (snapshot?.cameras ?? []).filter((c) => !!c.recalibrate_required_at).length

  const alertCounts = useMemo(() => {
    const alerts = snapshot?.active_alerts ?? []
    return Object.fromEntries(
      ALERT_TYPE_ORDER.map((t) => [t, alerts.filter((a) => a.alert_type === t).length]),
    ) as Record<AlertType, number>
  }, [snapshot?.active_alerts])

  const apiStatus: ServiceStatus = healthPending ? 'loading' : health?.status === 'ok' ? 'ok' : 'fail'
  const dbStatus: ServiceStatus = readyPending ? 'loading' : ready?.db === 'ok' ? 'ok' : 'fail'
  const redisStatus: ServiceStatus = readyPending ? 'loading' : ready?.redis === 'ok' ? 'ok' : 'fail'

  return (
    <>
      <Helmet title="System Dashboard — Admin" />
      <div className="p-6 max-w-4xl space-y-6">
        <PageHeader title="System Dashboard" />

        {/* ── Service health ────────────────────────────────────────────── */}
        <section aria-label="System health">
          <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            Service Health
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <ServiceRow name="API" status={apiStatus} />
            <ServiceRow name="Database" status={dbStatus} />
            <ServiceRow name="Redis" status={redisStatus} />
            <div className="flex items-center justify-between rounded-xl border border-border bg-surface-base px-4 py-3 shadow-1 hover:shadow-2 transition-shadow duration-fast cursor-default">
              <p className="text-[13px] font-medium text-text-primary">Version</p>
              <p className="font-mono text-[13px] font-semibold text-text-secondary">
                {healthPending ? (
                  <span className="inline-block h-4 w-10 animate-pulse rounded bg-surface-sunken" />
                ) : (
                  (health?.version ?? '—')
                )}
              </p>
            </div>
          </div>
        </section>

        {/* ── Metrics + derived stats ───────────────────────────────────── */}
        <section aria-label="System metrics" className="space-y-4">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            Overview
          </h2>

          {/* KPI row */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <KpiCard
              label="Head Count"
              value={snapshot?.head_count?.plant_total ?? '—'}
              icon={Users}
              to="/admin/persons"
              accent="bg-brand-500/10 text-brand-500"
              isPending={!snapshot}
            />
            <KpiCard
              label="Cameras Online"
              value={totalCameras > 0 ? `${activeCameras}/${totalCameras}` : '—'}
              icon={Camera}
              to="/admin/cameras"
              accent="bg-success/10 text-success"
            />
            <KpiCard
              label="Active Alerts"
              value={snapshot?.active_alerts?.length ?? '—'}
              icon={Bell}
              to="/admin/alert-routing"
              accent="bg-warning/10 text-warning"
            />
          </div>

          {/* Alert type breakdown */}
          {snapshot && (
            <div>
              <p className="mb-2 text-[11px] font-medium text-text-muted">Alert Breakdown</p>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
                {ALERT_TYPE_ORDER.map((type) => {
                  const meta = ALERT_TYPE_META[type]
                  const count = alertCounts[type] ?? 0
                  const Icon = meta.icon
                  return (
                    <div
                      key={type}
                      className="flex flex-col items-center gap-1 rounded-xl border border-border bg-surface-base px-3 py-3 shadow-1 hover:shadow-2 transition-shadow duration-fast cursor-default"
                    >
                      <Icon className={`h-4 w-4 ${count > 0 ? meta.accent : 'text-text-muted'}`} aria-hidden="true" />
                      <p className={`tabular-nums text-[22px] font-bold leading-none ${count > 0 ? 'text-text-primary' : 'text-text-muted'}`}>
                        {count}
                      </p>
                      <p className="text-[10px] font-medium text-text-muted">{meta.label}</p>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Camera health summary */}
          {snapshot && totalCameras > 0 && (
            <div>
              <p className="mb-2 text-[11px] font-medium text-text-muted">Camera Health</p>
              <div className="flex flex-wrap gap-3">
                {[
                  { label: 'Total', value: totalCameras, color: 'text-text-secondary bg-surface-sunken' },
                  { label: 'Online', value: activeCameras, color: 'text-success bg-success/10' },
                  { label: 'Offline', value: offlineCameras, color: offlineCameras > 0 ? 'text-error bg-error/10' : 'text-text-muted bg-surface-sunken' },
                  { label: 'Calibration', value: needsCalibration, color: needsCalibration > 0 ? 'text-warning bg-warning/10' : 'text-text-muted bg-surface-sunken' },
                ].map(({ label, value, color }) => (
                  <div key={label} className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 ${color}`}>
                    <span className="text-[13px] font-bold tabular-nums">{value}</span>
                    <span className="text-[11px] font-medium">{label}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        {/* ── Quick access ──────────────────────────────────────────────── */}
        <section aria-label="Quick access">
          <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
            Quick Access
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { to: '/admin/cameras', label: 'Cameras', icon: Camera, desc: 'Manage streams' },
              { to: '/admin/persons', label: 'Persons', icon: Users, desc: 'Identity database' },
              { to: '/admin/anomaly-detectors', label: 'Anomaly', icon: Zap, desc: 'Detection rules' },
              { to: '/admin/alert-routing', label: 'Alerts', icon: Bell, desc: 'Routing & dispatch' },
            ].map(({ to, label, icon: Icon, desc }) => (
              <Link
                key={to}
                to={to}
                className="group rounded-xl border border-border bg-surface-base p-5 shadow-1 transition-[box-shadow,border-color] duration-fast hover:shadow-2 hover:border-action-700/30"
              >
                <Icon
                  className="mb-2 h-5 w-5 text-text-muted transition-colors group-hover:text-action-700"
                  aria-hidden="true"
                />
                <p className="text-[13px] font-semibold text-text-primary">{label}</p>
                <p className="mt-0.5 text-[12px] text-text-muted">{desc}</p>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </>
  )
}
