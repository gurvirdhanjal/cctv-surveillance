import { memo, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { MonitorPlay, Tv2, Settings2, Bookmark } from 'lucide-react'
import { cn } from '@/shared/utils/cn'
import { useCameraSnapshot } from '../hooks/useCameraSnapshot'
import { FloatingActionBar } from '@/shared/design-system/components/FloatingActionBar'
import type { CameraState } from '../types'

export const CAMERA_TILE_HOVER_SCALE = 1.02

interface CameraTileProps {
  camera: CameraState
  isFocused: boolean
  isAlarming?: boolean
  recording?: boolean
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
  recording = false,
  onSelect,
}: CameraTileProps) {
  const snapshotUrl = useCameraSnapshot(camera.camera_id)
  const prefersReduced = useReducedMotion()
  const [hovered, setHovered] = useState(false)

  const hasPtz = camera.capability_tier === 'FULL'

  const fabActions = [
    { icon: MonitorPlay, label: 'Live', onClick: onSelect },
    { icon: Tv2, label: 'Playback', onClick: () => {} },
    { icon: Settings2, label: 'PTZ', onClick: () => {}, disabled: !hasPtz },
    { icon: Bookmark, label: 'Bookmark', onClick: () => {} },
  ]

  return (
    <div
      className="relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <motion.button
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
        whileHover={prefersReduced ? undefined : { scale: CAMERA_TILE_HOVER_SCALE }}
        transition={{ duration: 0.08, ease: [0.4, 0, 0.2, 1] }}
      >
        {/* Header bar */}
        <div className="flex items-center justify-between gap-1 px-1.5 py-1 bg-black/30">
          <div className="flex items-center gap-1">
            <span
              className={cn('h-1.5 w-1.5 rounded-full', statusDot[camera.status])}
              aria-hidden="true"
            />
            {recording && (
              <span
                className="rounded px-1 text-[9px] font-semibold uppercase text-red-400 bg-red-400/10"
                aria-label="Recording"
              >
                REC
              </span>
            )}
          </div>
          <span
            className={cn('flex-shrink-0 rounded-full bg-[#232d42] px-1.5 text-[9px]', tierBadge[camera.capability_tier])}
          >
            {camera.capability_tier}
          </span>
        </div>

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
        </div>

        {/* Body */}
        <div className="px-1.5 py-1.5 space-y-0.5">
          <span className="block truncate text-[11px] text-slate-200">{camera.name}</span>
          <span className="block text-[9px] text-slate-500">
            {camera.capability_tier === 'FULL'
              ? 'Face · Body · Anomaly'
              : camera.capability_tier === 'MID'
                ? 'Face · Body'
                : 'Body only'}
          </span>
        </div>
      </motion.button>

      {(hovered || prefersReduced) && (
        <FloatingActionBar actions={fabActions} />
      )}
    </div>
  )
})
