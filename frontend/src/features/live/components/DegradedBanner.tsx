import { useLiveStore } from '../store/liveStore'

export function DegradedBanner() {
  const degraded = useLiveStore((s) => s.degraded)
  if (!degraded) return null

  return (
    <div
      role="status"
      aria-label="Connection degraded"
      aria-live="polite"
      className="flex items-center gap-2 bg-amber-100 border-b border-amber-300 px-4 py-2 text-[13px] text-amber-900"
    >
      <span className="inline-block h-2 w-2 rounded-full bg-amber-500 animate-pulse" aria-hidden="true" />
      Reconnecting&hellip; Some live data may be stale.
    </div>
  )
}
