import { memo } from 'react'
import { cn } from '@/shared/utils/cn'
import type { LiveAlert } from '../types'

interface AlertCardProps {
  alert: LiveAlert
  cameraName?: string
  onAcknowledge?: (id: number) => void
  onResolve?: (id: number) => void
}

const severityBar: Record<string, string> = {
  CRITICAL: 'bg-severity-critical',
  HIGH: 'bg-severity-high',
  MEDIUM: 'bg-severity-medium',
  LOW: 'bg-severity-low',
}

const severityText: Record<string, string> = {
  CRITICAL: 'text-severity-critical',
  HIGH: 'text-severity-high',
  MEDIUM: 'text-severity-medium',
  LOW: 'text-severity-low',
}

const ACRONYMS = new Set(['PPE', 'ID'])

function formatAlertType(t: string): string {
  return t
    .split('_')
    .map((word) => ACRONYMS.has(word) ? word : word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ')
}

function timeSince(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diffMs / 60_000)
  if (m < 1) return 'Just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return h < 24 ? `${h}h ago` : `${Math.floor(h / 24)}d ago`
}

export const AlertCard = memo(function AlertCard({
  alert,
  cameraName,
  onAcknowledge,
  onResolve,
}: AlertCardProps) {
  const camLabel = cameraName ?? (alert.camera_id !== null ? `Cam #${alert.camera_id}` : null)
  const location = [
    camLabel,
    alert.zone_id !== null && `Zone #${alert.zone_id}`,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <div
      className="flex gap-2 rounded-lg bg-surface-raised p-3"
      role="article"
      aria-label={`${alert.severity} alert: ${formatAlertType(alert.alert_type)}`}
    >
      {/* Severity colour bar */}
      <div
        className={cn('w-1 flex-shrink-0 rounded-full', severityBar[alert.severity])}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        {/* Header row */}
        <div className="flex items-center gap-2">
          <span
            className={cn('text-[11px] font-semibold uppercase tracking-wide', severityText[alert.severity])}
          >
            {alert.severity}
          </span>
          <span className="text-[11px] text-text-muted">{timeSince(alert.triggered_at)}</span>
        </div>
        {/* Type */}
        <p className="mt-0.5 text-[13px] font-medium text-text-primary">
          {formatAlertType(alert.alert_type)}
        </p>
        {/* Location */}
        {location && (
          <p className="mt-0.5 text-[12px] text-text-muted">{location}</p>
        )}
        {/* CTAs */}
        {alert.state === 'OPEN' && (
          <div className="mt-2 flex gap-3">
            {onAcknowledge && (
              <button
                type="button"
                className="text-[12px] font-medium text-brand-500 hover:text-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
                onClick={() => onAcknowledge(alert.alert_id)}
              >
                Acknowledge
              </button>
            )}
            {onResolve && (
              <button
                type="button"
                className="text-[12px] font-medium text-text-muted hover:text-text-secondary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
                onClick={() => onResolve(alert.alert_id)}
              >
                Resolve
              </button>
            )}
          </div>
        )}
        {alert.state !== 'OPEN' && (
          <p className="mt-1 text-[11px] uppercase tracking-wide text-text-muted">
            {alert.state}
          </p>
        )}
      </div>
    </div>
  )
})
