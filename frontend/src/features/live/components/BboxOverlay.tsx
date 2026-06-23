import { useTrackedPersons } from '../hooks/useTrackedPersons'

interface BboxOverlayProps {
  cameraId: number
}

/**
 * SVG overlay for the focused camera. Renders a bounding box per tracked person.
 * Named persons: solid brand-blue stroke. Unknown: red dashed stroke.
 *
 * NOTE: rAF-batched direct DOM writes (§15) are added in Phase 4F when the
 * socket dispatch layer is wired. For Phase 4C the component re-renders via
 * React normally (triggered by liveStore trackedPersons changes).
 */
export function BboxOverlay({ cameraId }: BboxOverlayProps) {
  const persons = useTrackedPersons(cameraId)

  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      aria-hidden="true"
    >
      {persons.map((loc) => {
        const [x1, y1, x2, y2] = loc.bbox
        const isKnown = loc.person_id !== null
        return (
          <g key={loc.global_track_id}>
            <rect
              x={`${x1 * 100}%`}
              y={`${y1 * 100}%`}
              width={`${(x2 - x1) * 100}%`}
              height={`${(y2 - y1) * 100}%`}
              fill="none"
              stroke={isKnown ? '#2b6cb0' : '#dc2626'}
              strokeWidth={2}
              strokeDasharray={isKnown ? undefined : '4 2'}
              data-track-id={loc.global_track_id}
            />
            {isKnown && (
              <text
                x={`${x1 * 100}%`}
                y={`${y1 * 100 - 2}%`}
                fill="#2b6cb0"
                fontSize={10}
                fontFamily="sans-serif"
              >
                {`#${loc.person_id}`}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
