import { useLiveStore } from '../store/liveStore'

const WINDOW_S = 3600
const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: 'var(--alarm-red, #ef4444)',
  HIGH: '#f59e0b',
  MEDIUM: '#eab308',
  LOW: 'var(--text-muted, #64748b)',
}

interface Props {
  onSeek?: (alertId: number) => void
}

export function AlertTimeline({ onSeek }: Props) {
  const alerts = useLiveStore((s) => s.alerts)
  const nowMs = Date.now()

  const recent = alerts.filter((a) => {
    const ageS = (nowMs - new Date(a.triggered_at).getTime()) / 1000
    return ageS <= WINDOW_S
  })

  return (
    <div
      className="relative w-full overflow-hidden border-t border-[#1e293b] bg-[#0a0e1a]"
      style={{ height: '120px' }}
    >
      {recent.length === 0 ? (
        <div className="flex h-full items-center justify-center">
          <span className="text-[11px] text-text-muted">No alerts in the last 60 minutes</span>
        </div>
      ) : (
        <>
          {recent.map((alert) => {
            const ageS = (nowMs - new Date(alert.triggered_at).getTime()) / 1000
            const pct = ((WINDOW_S - ageS) / WINDOW_S) * 100
            return (
              <button
                key={alert.alert_id}
                type="button"
                data-alert-mark={alert.alert_id}
                aria-label={`Alert ${alert.alert_id} — ${alert.severity}`}
                onClick={() => onSeek?.(alert.alert_id)}
                style={{
                  position: 'absolute',
                  left: `${pct}%`,
                  top: '50%',
                  transform: 'translate(-50%, -50%)',
                  width: '3px',
                  height: '48px',
                  backgroundColor: SEVERITY_COLOR[alert.severity] ?? SEVERITY_COLOR.LOW,
                  border: 'none',
                  cursor: 'pointer',
                  padding: 0,
                  borderRadius: '1px',
                }}
              />
            )
          })}
          <div
            className="pointer-events-none absolute bottom-1 left-2 text-[10px] text-text-muted"
          >
            60 min ago
          </div>
          <div
            className="pointer-events-none absolute bottom-1 right-2 text-[10px] text-text-muted"
          >
            now
          </div>
        </>
      )}
    </div>
  )
}
