import { memo } from 'react'
import { cn } from '@/shared/utils/cn'
import { useCameraSnapshot } from '../hooks/useCameraSnapshot'
import type { CameraState } from '../types'

interface CameraTileProps {
  camera: CameraState
  isFocused: boolean
  onSelect: () => void
}

const tierColors: Record<string, string> = {
  FULL: 'bg-brand-500 text-white',
  MID: 'bg-brand-300 text-brand-900',
  LOW: 'bg-surface-sunken text-text-muted border border-border',
}

const statusDot: Record<string, string> = {
  online: 'bg-status-online',
  offline: 'bg-status-offline',
  auth_failed: 'bg-status-auth-failed',
  maintenance: 'bg-status-maintenance',
}

export const CameraTile = memo(function CameraTile({
  camera,
  isFocused,
  onSelect,
}: CameraTileProps) {
  const snapshotUrl = useCameraSnapshot(camera.camera_id)

  return (
    <button
      type="button"
      className={cn(
        'relative flex w-full flex-col rounded-lg border bg-surface-raised p-1.5 text-left transition-colors',
        isFocused
          ? 'border-brand-500 ring-2 ring-brand-500/30'
          : 'border-border hover:border-border-strong',
        camera.status === 'auth_failed' && !isFocused && 'border-status-auth-failed',
        camera.status === 'maintenance' && 'opacity-60',
      )}
      onClick={onSelect}
      aria-pressed={isFocused}
      aria-label={camera.name}
    >
      {/* Snapshot image */}
      <div className="relative aspect-video w-full overflow-hidden rounded bg-surface-sunken">
        {snapshotUrl && camera.status === 'online' ? (
          <img
            src={snapshotUrl}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <span
              className={cn('h-2 w-2 rounded-full', statusDot[camera.status])}
              aria-hidden="true"
            />
          </div>
        )}
        {camera.status === 'maintenance' && (
          <div
            className="absolute inset-0 flex items-center justify-center bg-black/40"
            aria-label="Under maintenance"
          >
            <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
          </div>
        )}
      </div>
      {/* Footer */}
      <div className="mt-1 flex items-center justify-between gap-1 px-0.5">
        <span className="truncate text-[11px] font-medium text-text-primary">{camera.name}</span>
        <span
          className={cn('flex-shrink-0 rounded px-1 py-0.5 text-[9px] font-semibold', tierColors[camera.capability_tier])}
        >
          {camera.capability_tier}
        </span>
      </div>
    </button>
  )
})
