import type { ForensicClip } from '@/shared/api/types'

interface ClipResultCardProps {
  clip: ForensicClip
  onClick: () => void
}

export function ClipResultCard({ clip, onClick }: ClipResultCardProps) {
  return (
    <button
      onClick={onClick}
      className="w-full rounded-lg border border bg-surface-base text-left shadow-1 transition-shadow hover:shadow-2 focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)]"
      aria-label={`Clip from camera ${clip.camera_id}`}
    >
      <div className="aspect-video overflow-hidden rounded-t-lg bg-surface-sunken">
        {clip.thumbnail_url ? (
          <img
            src={clip.thumbnail_url}
            alt="Clip thumbnail"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <svg
              className="h-8 w-8 text-text-muted"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.89L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
              />
            </svg>
          </div>
        )}
      </div>

      <div className="p-3">
        <p className="text-[12px] font-medium text-text-primary">
          Camera {clip.camera_id}
          {clip.zone_id != null ? ` · Zone ${clip.zone_id}` : ''}
        </p>
        <p className="mt-0.5 text-[11px] text-text-muted">
          {new Date(clip.triggered_at).toLocaleString()}
        </p>
        <div className="mt-1 flex items-center">
          {clip.duration_s != null && (
            <span className="text-[11px] text-text-muted">{clip.duration_s}s</span>
          )}
          <span className="ml-auto rounded-full bg-brand-50 px-2 py-0.5 text-[10px] font-semibold text-brand-700">
            Score {(clip.score * 100).toFixed(0)}%
          </span>
        </div>
      </div>
    </button>
  )
}
