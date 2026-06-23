import { useState, useMemo } from 'react'
import { useLiveStore } from '../store/liveStore'
import { useLiveAlerts } from '../hooks/useLiveAlerts'
import { AlertCard } from './AlertCard'
import type { LiveAlert } from '../types'

type SeverityFilter = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | ''

const severityOrder: Record<string, number> = {
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
}

export function AlertSidebar() {
  const alerts = useLiveStore((s) => s.alerts)
  const degraded = useLiveStore((s) => s.degraded)
  const setFocusedCamera = useLiveStore((s) => s.setFocusedCamera)
  const { acknowledge, resolve } = useLiveAlerts()

  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('')

  const sorted = useMemo(() => {
    const filtered = severityFilter
      ? alerts.filter((a) => a.severity === severityFilter)
      : alerts

    return [...filtered].sort((a, b) => {
      const sevDiff = (severityOrder[a.severity] ?? 99) - (severityOrder[b.severity] ?? 99)
      if (sevDiff !== 0) return sevDiff
      return new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime()
    })
  }, [alerts, severityFilter])

  // Group by global_track_id (or alert_id when null)
  const grouped = useMemo(() => {
    const groups = new Map<string, LiveAlert[]>()
    for (const alert of sorted) {
      const key = alert.global_track_id ?? `solo-${alert.alert_id}`
      const list = groups.get(key) ?? []
      list.push(alert)
      groups.set(key, list)
    }
    return Array.from(groups.values())
  }, [sorted])

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-border px-3 py-2">
        <div className="flex items-center justify-between">
          <h2 className="text-[13px] font-semibold text-text-primary">
            Alerts
            {sorted.length > 0 && (
              <span className="ml-1.5 rounded-full bg-severity-high/10 px-1.5 py-0.5 text-[11px] text-severity-high">
                {sorted.length}
              </span>
            )}
          </h2>
        </div>
        <select
          className="mt-2 w-full rounded border border-border bg-surface-base px-2 py-1 text-[12px] text-text-primary"
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value as SeverityFilter)}
          aria-label="Filter by severity"
        >
          <option value="">All severities</option>
          <option value="CRITICAL">Critical</option>
          <option value="HIGH">High</option>
          <option value="MEDIUM">Medium</option>
          <option value="LOW">Low</option>
        </select>
      </div>

      {/* Degraded banner */}
      {degraded && (
        <div
          className="flex-shrink-0 bg-warning/10 px-3 py-1.5 text-[12px] text-warning"
          role="status"
        >
          Alerts paused — system degraded
        </div>
      )}

      {/* Alert list */}
      <div className="flex-1 overflow-y-auto p-2">
        {grouped.length === 0 ? (
          <p className="py-8 text-center text-[13px] text-text-muted">No active alerts</p>
        ) : (
          <div className="flex flex-col gap-2">
            {grouped.map((group) => {
              const primary = group[0]
              return (
                <div
                  key={primary.global_track_id ?? primary.alert_id}
                  role="listitem"
                  onClick={() => {
                    if (primary.camera_id !== null) setFocusedCamera(primary.camera_id)
                  }}
                  className="cursor-pointer"
                >
                  <AlertCard
                    alert={primary}
                    onAcknowledge={acknowledge}
                    onResolve={resolve}
                  />
                  {group.length > 1 && (
                    <p className="mt-1 pl-3 text-[11px] text-text-muted">
                      +{group.length - 1} similar
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
