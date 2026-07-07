import { memo } from 'react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/shared/design-system/components/ui/Collapsible'
import { cn } from '@/shared/utils/cn'
import { useCountdown } from '../hooks/useCountdown'
import type { LiveAlert } from '../types'

const DEFAULT_SLA_WINDOW_S = 900

const severityBorder: Record<string, string> = {
  CRITICAL: 'border-l-[#dc2626]',
  HIGH: 'border-l-[#ea580c]',
  MEDIUM: 'border-l-[#d97706]',
  LOW: 'border-l-[#65a30d]',
}

const severityText: Record<string, string> = {
  CRITICAL: 'text-[#dc2626]',
  HIGH: 'text-[#ea580c]',
  MEDIUM: 'text-[#d97706]',
  LOW: 'text-[#65a30d]',
}

const slaBarColor: Record<string, string> = {
  ok: 'bg-slate-400',
  warn: 'bg-amber-500',
  crit: 'bg-[#dc2626]',
}

const ACRONYMS = new Set(['PPE', 'ID'])

function formatAlertType(t: string): string {
  return t
    .split('_')
    .map((w) => ACRONYMS.has(w) ? w : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ')
}

function timeSince(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diffMs / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return h < 24 ? `${h}h ago` : `${Math.floor(h / 24)}d ago`
}

interface AlarmCardProps {
  alert: LiveAlert
  cameraName?: string
  similarAlerts?: LiveAlert[]
  isSelected?: boolean
  onAcknowledge?: (id: number) => void
  onResolve?: (id: number) => void
  onBookmark?: (id: number) => void
  onExport?: (id: number) => void
}

export const AlarmCard = memo(function AlarmCard({
  alert,
  cameraName,
  similarAlerts,
  isSelected,
  onAcknowledge,
  onResolve,
  onBookmark,
  onExport,
}: AlarmCardProps) {
  const camLabel = cameraName ?? (alert.camera_id !== null ? `Cam #${alert.camera_id}` : null)
  const sla = useCountdown(alert.sla_deadline ?? null, DEFAULT_SLA_WINDOW_S)
  const hasSla = Boolean(alert.sla_deadline)
  const similarCount = similarAlerts?.length ?? 0

  return (
    <div
      role="article"
      aria-label={`${alert.severity} alert: ${formatAlertType(alert.alert_type)}`}
      className={cn(
        'rounded-xl border-l-4 bg-[#1a2234] p-3',
        severityBorder[alert.severity] ?? 'border-l-slate-600',
        isSelected && 'ring-2 ring-action-600',
      )}
    >
      {/* Row 1: type + timestamp */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <span
            className={cn('text-[11px] font-semibold uppercase tracking-wide', severityText[alert.severity])}
          >
            {alert.severity}
          </span>
          <p className="mt-0.5 text-[13px] font-medium text-slate-100">
            {formatAlertType(alert.alert_type)}
          </p>
          {camLabel && (
            <p className="mt-0.5 text-[12px] text-slate-400">{camLabel}</p>
          )}
        </div>
        <span className="flex-shrink-0 font-mono text-[11px] text-slate-400">
          {timeSince(alert.triggered_at)}
        </span>
      </div>

      {/* SLA countdown bar */}
      {hasSla && (
        <div className="mt-2">
          <div className="h-1 w-full overflow-hidden rounded-full bg-[#232d42]">
            <div
              className={cn('h-full rounded-full', slaBarColor[sla.tier])}
              style={{ width: `${sla.fraction * 100}%` }}
              role="progressbar"
              aria-label="SLA countdown"
              aria-valuenow={sla.secondsRemaining}
              aria-valuemin={0}
              aria-valuemax={DEFAULT_SLA_WINDOW_S}
            />
          </div>
          <p className="mt-0.5 font-mono text-[11px] text-slate-400">
            {sla.secondsRemaining}s remaining
          </p>
        </div>
      )}

      {/* Actions */}
      {alert.state === 'OPEN' && (
        <div className="mt-2 flex flex-wrap gap-2">
          {onAcknowledge && (
            <button
              type="button"
              className="rounded-[10px] bg-action-600 px-2.5 py-1 text-[12px] font-medium text-white hover:bg-action-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
              onClick={() => onAcknowledge(alert.alert_id)}
            >
              Acknowledge
            </button>
          )}
          {onResolve && (
            <button
              type="button"
              className="rounded-[10px] bg-[#232d42] px-2.5 py-1 text-[12px] font-medium text-slate-300 hover:bg-[#2d3a50] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
              onClick={() => onResolve(alert.alert_id)}
            >
              Resolve
            </button>
          )}
          {onBookmark && (
            <button
              type="button"
              className="rounded-[10px] bg-[#232d42] px-2.5 py-1 text-[12px] font-medium text-slate-300 hover:bg-[#2d3a50] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
              onClick={() => onBookmark(alert.alert_id)}
            >
              Bookmark
            </button>
          )}
          {onExport && (
            <button
              type="button"
              className="rounded-[10px] bg-[#232d42] px-2.5 py-1 text-[12px] font-medium text-slate-300 hover:bg-[#2d3a50] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
              onClick={() => onExport(alert.alert_id)}
            >
              Export
            </button>
          )}
        </div>
      )}
      {alert.state !== 'OPEN' && (
        <p className="mt-1 text-[11px] uppercase tracking-wide text-slate-500">
          {alert.state}
        </p>
      )}

      {/* Similar alerts collapsible */}
      {similarCount > 0 && (
        <Collapsible className="mt-2">
          <CollapsibleTrigger className="text-[12px] text-slate-400 hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]">
            +{similarCount} similar
          </CollapsibleTrigger>
          <CollapsibleContent>
            <ul className="m-0 mt-1 list-none flex flex-col gap-1 pl-2 p-0">
              {similarAlerts!.map((sa) => (
                <li key={sa.alert_id} className="text-[12px] text-slate-500">
                  {formatAlertType(sa.alert_type)} — {timeSince(sa.triggered_at)}
                </li>
              ))}
            </ul>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  )
})
