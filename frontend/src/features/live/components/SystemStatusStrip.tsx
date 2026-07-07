import { useLiveStore } from '../store/liveStore'

function ConnectionDot({ wsStatus }: { wsStatus: 'connected' | 'reconnecting' | 'offline' }) {
  const color =
    wsStatus === 'connected'
      ? 'bg-[#22c55e]'
      : wsStatus === 'reconnecting'
        ? 'bg-amber-400'
        : 'bg-[#dc2626]'
  const label =
    wsStatus === 'connected' ? 'Connected' : wsStatus === 'reconnecting' ? 'Reconnecting' : 'Offline'
  return (
    <span className="flex items-center gap-1.5">
      <span className={`h-2 w-2 rounded-full ${color}`} aria-hidden="true" />
      <span>{label}</span>
    </span>
  )
}

export function SystemStatusStrip() {
  const cameras = useLiveStore((s) => s.cameras)
  const headCount = useLiveStore((s) => s.headCount)
  const gpuPct = useLiveStore((s) => s.gpuPct)
  const wsStatus = useLiveStore((s) => s.wsStatus)
  const alerts = useLiveStore((s) => s.alerts)

  const onlineCount = cameras.filter((c) => c.status === 'online').length
  const offlineCount = cameras.length - onlineCount
  const lastAlert = alerts[0]
  const lastEventLabel = lastAlert
    ? new Date(lastAlert.triggered_at).toLocaleTimeString()
    : '—'

  return (
    <div
      aria-label="System status"
      className="flex h-8 flex-shrink-0 items-center gap-6 border-t border-[#1e293b] bg-[#111827] px-4 text-[11px] text-slate-400"
    >
      <span>
        <span
          className={onlineCount > 0 ? 'text-slate-200' : undefined}
          aria-label={`${onlineCount} cameras online`}
        >
          {onlineCount}
        </span>
        {' / '}
        {cameras.length} cameras
        {offlineCount > 0 && (
          <span className="ml-1 text-[#dc2626]" aria-label={`${offlineCount} offline`}>
            ({offlineCount} offline)
          </span>
        )}
      </span>

      <span className="font-mono" aria-label={`${headCount.total} people on site`}>
        {headCount.total} on-site
      </span>

      <span className="font-mono" aria-label={`GPU ${gpuPct}%`}>
        GPU {gpuPct}%
      </span>

      <span aria-label={`Last event at ${lastEventLabel}`}>
        Last event: {lastEventLabel}
      </span>

      <div className="ml-auto">
        <ConnectionDot wsStatus={wsStatus} />
      </div>
    </div>
  )
}
