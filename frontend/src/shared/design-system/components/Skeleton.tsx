import type { CSSProperties } from 'react'
import { cn } from '@/shared/utils/cn'

interface SkeletonProps {
  className?: string
  style?: CSSProperties
}

export function Skeleton({ className, style }: SkeletonProps) {
  return (
    <div
      className={cn('animate-pulse rounded bg-surface-raised', className)}
      style={style}
      aria-hidden="true"
    />
  )
}

export function SkeletonText({ lines = 2, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn('space-y-2', className)}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={cn('h-4', i === lines - 1 && lines > 1 ? 'w-3/4' : 'w-full')} />
      ))}
    </div>
  )
}

export function SkeletonTable({ rows = 8, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('space-y-px', className)}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-3 border-b border-border" aria-hidden="true">
          <Skeleton className="h-8 w-8 rounded-full flex-shrink-0" />
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-1/3" />
            <Skeleton className="h-3 w-1/4" />
          </div>
          <Skeleton className="h-3 w-16" />
        </div>
      ))}
    </div>
  )
}

export function SkeletonKpiGrid({ cards = 4, className }: { cards?: number; className?: string }) {
  return (
    <div className={cn('grid grid-cols-2 gap-3 sm:grid-cols-4', className)}>
      {Array.from({ length: cards }, (_, i) => (
        <div key={i} className="rounded-xl border border-border bg-surface-base p-4 space-y-3" aria-hidden="true">
          <Skeleton className="h-3 w-1/2" />
          <Skeleton className="h-7 w-2/3" />
        </div>
      ))}
    </div>
  )
}

// ─── §L spec composites ────────────────────────────────────────────

/** §L KPI card skeleton — matches a single metric card (label + value + trend). */
export function SkeletonKpiCard({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn('rounded-xl bg-surface-raised p-4 space-y-3', className)}
    >
      <Skeleton className="h-3 w-2/5" />
      <Skeleton className="h-7 w-1/2" />
      <Skeleton className="h-2.5 w-1/3" />
    </div>
  )
}

/** §L camera card skeleton — matches a CameraCard layout (preview + meta). */
export function SkeletonCameraCard({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn('rounded-xl bg-surface-raised overflow-hidden', className)}
    >
      {/* preview area */}
      <Skeleton className="h-36 w-full rounded-none" />
      <div className="p-3 space-y-2">
        <Skeleton className="h-3.5 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </div>
  )
}

/** §L table row skeleton — one bar per column at the hinted width. */
export function SkeletonTableRow({
  columnWidths,
  className,
}: {
  columnWidths?: number[]
  className?: string
}) {
  const cols = columnWidths ?? [120, 200, 80]
  return (
    <div
      aria-hidden="true"
      className={cn('flex items-center gap-4 px-4 py-2.5', className)}
    >
      {cols.map((w, i) => (
        <Skeleton
          key={i}
          className="h-3 flex-shrink-0"
          style={{ width: `${w}px` }}
        />
      ))}
    </div>
  )
}

/** §L avatar skeleton — circular, matches a user/person avatar. */
export function SkeletonAvatar({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <Skeleton
      className={cn('rounded-full flex-shrink-0', className)}
      style={{ width: size, height: size }}
    />
  )
}

/** §V.2 chart skeleton — full-width shimmer block matching ECharts container height. */
export function SkeletonChart({ className, style }: { className?: string; style?: CSSProperties }) {
  return (
    <div
      role="status"
      aria-label="Loading chart"
      className={cn('animate-pulse rounded-xl bg-surface-raised w-full', className)}
      style={{ height: 192, ...style }}
    />
  )
}

/** §Q camera tree skeleton — 3 group headers + 4 camera-row skeletons. */
export function SkeletonCameraTree({ className }: { className?: string }) {
  return (
    <div className={cn('space-y-1 p-2', className)} aria-hidden="true">
      {Array.from({ length: 3 }, (_, g) => (
        <div key={g} className="space-y-1">
          {/* Group header */}
          <div className="flex items-center gap-2 px-2 py-1">
            <Skeleton className="h-3 w-3 rounded-sm flex-shrink-0" />
            <Skeleton className={cn('h-3', g === 0 ? 'w-24' : g === 1 ? 'w-20' : 'w-28')} />
          </div>
          {/* Camera rows (only first group shows rows) */}
          {g === 0 &&
            Array.from({ length: 4 }, (_, r) => (
              <div key={r} className="flex items-center gap-2 px-4 py-0.5">
                <Skeleton className="h-2 w-2 rounded-full flex-shrink-0" />
                <Skeleton className={cn('h-3', r % 2 === 0 ? 'w-32' : 'w-24')} />
              </div>
            ))}
        </div>
      ))}
    </div>
  )
}

/** §I alert timeline skeleton — full-width bar with 8 evenly-spaced marks. */
export function SkeletonTimeline({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn('relative w-full overflow-hidden', className)}
      style={{ height: '120px' }}
    >
      <Skeleton className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 rounded-none" />
      {Array.from({ length: 8 }, (_, i) => (
        <Skeleton
          key={i}
          className="absolute top-1/2 -translate-y-1/2 w-0.5 h-12"
          style={{ left: `${(i + 1) * (100 / 9)}%` }}
        />
      ))}
    </div>
  )
}
