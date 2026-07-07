import { memo } from 'react'
import { cn } from '@/shared/utils/cn'
import { useCameraSnapshot } from '../hooks/useCameraSnapshot'
import type { CameraState } from '../types'

interface CameraTileProps {
  camera: CameraState
  isFocused: boolean
  isAlarming?: boolean
  onSelect: () => void
}

const tierBadge: Record<string, string> = {
  FULL: 'text-white',
  MID: 'text-slate-300',
  LOW: 'text-slate-400',
}

const statusDot: Record<string, string> = {
  online: 'bg-[#22c55e]',
  offline: 'bg-slate-500',
  auth_failed: 'bg-amber-400',
  maintenance: 'bg-blue-400',
}

export const CameraTile = memo(function CameraTile({
  camera,
  isFocused,
  isAlarming,
  onSelect,
}: CameraTileProps) {
  const snapshotUrl = useCameraSnapshot(camera.camera_id)

  return (
    <button
      type="button"
      className={cn(
        'relative flex w-full cursor-pointer flex-col overflow-hidden rounded-xl border bg-[#1a2234] text-left transition-colors',
        isFocused
          ? 'border-[#1e293b] ring-2 ring-white/40'
          : isAlarming
            ? 'animate-severity-pulse border-2 border-[#dc2626]'
            : 'border-[#1e293b] hover:border-[#334155]',
        camera.status === 'maintenance' && 'opacity-60',
      )}
      onClick={onSelect}
      aria-pressed={isFocused}
      aria-label={`Focus camera ${camera.name}`}
    >
      {/* Snapshot */}
      <div className="relative aspect-video w-full overflow-hidden bg-[#111827]">
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
        {/* Status dot top-left */}
        <span
          className={cn('absolute left-1.5 top-1.5 h-1.5 w-1.5 rounded-full', statusDot[camera.status])}
          aria-hidden="true"
        />
      </div>
      {/* Caption */}
      <div className="flex items-center justify-between gap-1 px-1.5 py-1">
        <span className="truncate text-[11px] text-slate-200">{camera.name}</span>
        <span
          className={cn('flex-shrink-0 rounded-full bg-[#232d42] px-1.5 text-[9px]', tierBadge[camera.capability_tier])}
        >
          {camera.capability_tier}
        </span>
      </div>
    </button>
  )
})
