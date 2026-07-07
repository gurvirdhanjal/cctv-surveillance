import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { useLiveStore } from '../store/liveStore'
import { useLiveAlerts } from '../hooks/useLiveAlerts'
import { AlarmCard } from './AlarmCard'
import { ScrollArea } from '@/shared/design-system/components/ui/ScrollArea'
import type { LiveAlert } from '../types'

type SeverityFilter = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | ''

const severityOrder: Record<string, number> = {
  CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3,
}

export function AlertSidebar() {
  const alerts = useLiveStore((s) => s.alerts)
  const cameras = useLiveStore((s) => s.cameras)
  const degraded = useLiveStore((s) => s.degraded)
  const setFocusedCamera = useLiveStore((s) => s.setFocusedCamera)
  const { acknowledge, resolve } = useLiveAlerts()

  const cameraNameById = useMemo(
    () => new Map(cameras.map((c) => [c.camera_id, c.name])),
    [cameras],
  )

  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('')
  const [selectedIndex, setSelectedIndex] = useState<number>(-1)

  const sorted = useMemo(() => {
    const filtered = severityFilter
      ? alerts.filter((a) => a.severity === severityFilter)
      : alerts
    return [...filtered].sort((a, b) => {
      const sd = (severityOrder[a.severity] ?? 99) - (severityOrder[b.severity] ?? 99)
      return sd !== 0 ? sd : new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime()
    })
  }, [alerts, severityFilter])

  // Group by global_track_id (or solo key)
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

  // Keep selectedIndex in range
  useEffect(() => {
    if (selectedIndex >= grouped.length) setSelectedIndex(grouped.length - 1)
  }, [grouped.length, selectedIndex])

  // ↑/↓ keyboard nav
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex((i) => Math.min(i + 1, grouped.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex((i) => Math.max(i - 1, 0))
      }
    },
    [grouped.length],
  )

  const listRef = useRef<HTMLUListElement>(null)

  return (
    <div
      className="flex h-full flex-col overflow-hidden"
      onKeyDown={handleKeyDown}
      tabIndex={-1}
    >
      {/* Header */}
      <div className="flex-shrink-0 border-b border-[#1e293b] px-3 py-2">
        <div className="flex items-center justify-between">
          <h2 className="text-[13px] font-semibold text-slate-100">
            Active Alerts
            {sorted.length > 0 && (
              <span className="ml-1.5 rounded-full bg-[#dc2626]/10 px-1.5 py-0.5 text-[11px] text-[#dc2626]">
                {sorted.length}
              </span>
            )}
          </h2>
        </div>
        <select
          className="mt-2 w-full rounded border border-[#1e293b] bg-[#1a2234] px-2 py-1 text-[12px] text-slate-200"
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
          className="flex-shrink-0 bg-amber-500/10 px-3 py-1.5 text-[12px] text-amber-400"
          role="status"
        >
          Alerts paused — system degraded
        </div>
      )}

      {/* Alert list */}
      <ScrollArea className="flex-1">
        <ul
          ref={listRef}
          className="flex flex-col gap-2 p-2"
          aria-live="assertive"
          aria-relevant="additions"
          aria-label="Active alert list"
        >
          {grouped.length === 0 ? (
            <li className="py-8 text-center text-[13px] text-slate-500">No active alerts</li>
          ) : (
            grouped.map((group, idx) => {
              const primary = group[0]
              const similar = group.slice(1)
              return (
                <li
                  key={primary.global_track_id ?? primary.alert_id}
                  onClick={() => {
                    setSelectedIndex(idx)
                    if (primary.camera_id !== null) setFocusedCamera(primary.camera_id)
                  }}
                  className="cursor-pointer"
                >
                  <AlarmCard
                    alert={primary}
                    cameraName={primary.camera_id !== null ? cameraNameById.get(primary.camera_id) : undefined}
                    similarAlerts={similar.length > 0 ? similar : undefined}
                    isSelected={idx === selectedIndex}
                    onAcknowledge={acknowledge}
                    onResolve={resolve}
                  />
                </li>
              )
            })
          )}
        </ul>
      </ScrollArea>

      {/* Shortcut legend footer */}
      <div className="flex-shrink-0 border-t border-[#1e293b] px-3 py-1.5 text-[11px] text-slate-500">
        <kbd className="rounded bg-[#232d42] px-1 font-mono text-[10px]">A</kbd> ack ·{' '}
        <kbd className="rounded bg-[#232d42] px-1 font-mono text-[10px]">R</kbd> resolve ·{' '}
        <kbd className="rounded bg-[#232d42] px-1 font-mono text-[10px]">↑↓</kbd> nav
      </div>
    </div>
  )
}
