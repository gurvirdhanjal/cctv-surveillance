import { memo } from 'react'
import { cn } from '@/shared/utils/cn'
import type { PersonLocation } from '../types'

interface PersonDotProps {
  location: PersonLocation
}

/**
 * A dot on the floor-plan showing a tracked person's position.
 * Uses inline style for position to allow direct DOM transform updates (§15).
 */
export const PersonDot = memo(function PersonDot({ location }: PersonDotProps) {
  const { floor_x, floor_y, person_id, global_track_id } = location
  const isKnown = person_id !== null

  return (
    <div
      data-track-id={global_track_id}
      style={{
        position: 'absolute',
        left: `${(floor_x ?? 0) * 100}%`,
        top: `${(floor_y ?? 0) * 100}%`,
        transform: 'translate(-50%, -50%)',
      }}
      className={cn(
        'h-3 w-3 rounded-full border-2 border-white',
        isKnown ? 'bg-brand-500' : 'bg-severity-critical',
      )}
      aria-label={isKnown ? `Person #${person_id}` : 'Unknown person'}
      role="img"
    />
  )
})
