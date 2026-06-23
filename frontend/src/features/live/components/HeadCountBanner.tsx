import { useState } from 'react'
import { cn } from '@/shared/utils/cn'
import { useLiveStore } from '../store/liveStore'

interface HeadCountBannerProps {
  className?: string
}

export function HeadCountBanner({ className }: HeadCountBannerProps) {
  const headCount = useLiveStore((s) => s.headCount)
  const degraded = useLiveStore((s) => s.degraded)
  const [expanded, setExpanded] = useState(false)

  const zoneEntries = Object.entries(headCount.byZone)

  return (
    <div className={cn('relative', className)}>
      <button
        type="button"
        className="flex items-center gap-1.5 rounded px-2 py-1 text-[13px] hover:bg-surface-sunken"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-label="Head count breakdown"
      >
        <span className="font-semibold text-text-primary">{headCount.total}</span>
        <span className="text-text-muted">in plant</span>
        {degraded && (
          <span className="rounded bg-warning/10 px-1 py-0.5 text-[10px] font-semibold text-warning" role="status">
            stale
          </span>
        )}
      </button>

      {expanded && (
        <div
          className="absolute right-0 top-full z-20 mt-1 min-w-[200px] rounded-lg border border-border bg-surface-raised p-3 shadow-2"
          role="region"
          aria-label="Per-zone head count"
        >
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
            By zone
          </p>
          {zoneEntries.length === 0 ? (
            <p className="text-[12px] text-text-muted">No zone data</p>
          ) : (
            zoneEntries.map(([zoneId, count]) => (
              <div key={zoneId} className="flex items-center justify-between py-0.5">
                <span className="text-[12px] text-text-secondary">Zone {zoneId}</span>
                <span className="text-[12px] font-semibold text-text-primary">{count}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
