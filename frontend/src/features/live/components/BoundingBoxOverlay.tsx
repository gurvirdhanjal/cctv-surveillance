import { useRef, useEffect } from 'react'
import { useTrackedPersons } from '../hooks/useTrackedPersons'
import { useLiveStore } from '../store/liveStore'

interface BoundingBoxOverlayProps {
  cameraId: number
}

// Color convention per plan §5 design rules
const COLOR_KNOWN = 'var(--brand-accent)'  // brass — identified/verified person; resolves from dark-theme ancestor
const COLOR_UNKNOWN = '#ef4444' // alarm red — unidentified
const COLOR_FOLLOWED = '#facc15' // yellow — operator follow-mode

const THROTTLE_MS = 200 // 5fps

export function BoundingBoxOverlay({ cameraId }: BoundingBoxOverlayProps) {
  const persons = useTrackedPersons(cameraId)
  const followedTrackId = useLiveStore((s) => s.followedTrackId)

  const svgRef = useRef<SVGSVGElement>(null)
  const pendingRef = useRef<typeof persons>(persons)
  const rafRef = useRef<number | null>(null)
  const lastFlushRef = useRef<number>(0)

  // Coalesce WS-driven re-renders to ≤5fps
  useEffect(() => {
    pendingRef.current = persons

    const now = Date.now()
    const sinceLastFlush = now - lastFlushRef.current
    if (sinceLastFlush >= THROTTLE_MS) {
      flushToSvg()
      return
    }

    if (rafRef.current === null) {
      rafRef.current = window.setTimeout(() => {
        rafRef.current = null
        flushToSvg()
      }, THROTTLE_MS - sinceLastFlush)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [persons])

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) {
        window.clearTimeout(rafRef.current)
        rafRef.current = null
      }
    }
  }, [])

  function flushToSvg() {
    lastFlushRef.current = Date.now()
    const svg = svgRef.current
    if (!svg) return
    // Direct DOM writes — bypass React to avoid extra re-renders
    const snap = pendingRef.current
    // Remove stale rects
    const existing = new Set(Array.from(svg.querySelectorAll('[data-track-id]')).map((el) => el.getAttribute('data-track-id')))
    const next = new Set(snap.map((p) => p.global_track_id))
    for (const old of existing) {
      if (!next.has(old)) svg.querySelector(`[data-track-id="${old}"]`)?.remove()
    }
    // Upsert rects
    for (const loc of snap) {
      const [x1, y1, x2, y2] = loc.bbox
      const isFollowed = loc.global_track_id === followedTrackId
      const color = isFollowed ? COLOR_FOLLOWED : loc.person_id !== null ? COLOR_KNOWN : COLOR_UNKNOWN
      let g = svg.querySelector(`[data-track-id="${loc.global_track_id}"]`) as SVGGElement | null
      if (!g) {
        g = document.createElementNS('http://www.w3.org/2000/svg', 'g')
        g.setAttribute('data-track-id', loc.global_track_id)
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
        rect.setAttribute('fill', 'none')
        rect.setAttribute('stroke-width', '2')
        rect.setAttribute('vector-effect', 'non-scaling-stroke')
        const label = document.createElementNS('http://www.w3.org/2000/svg', 'text')
        label.setAttribute('font-size', '10')
        label.setAttribute('font-family', 'monospace')
        g.appendChild(rect)
        g.appendChild(label)
        svg.appendChild(g)
      }
      const rect = g.querySelector('rect')!
      const label = g.querySelector('text')!
      rect.setAttribute('x', String(x1 * 100) + '%')
      rect.setAttribute('y', String(y1 * 100) + '%')
      rect.setAttribute('width', String((x2 - x1) * 100) + '%')
      rect.setAttribute('height', String((y2 - y1) * 100) + '%')
      rect.setAttribute('stroke', color)
      if (isFollowed) {
        rect.setAttribute('filter', 'drop-shadow(0 0 4px rgba(250,204,21,0.8))')
      } else {
        rect.removeAttribute('filter')
      }
      label.setAttribute('x', String(x1 * 100) + '%')
      label.setAttribute('y', String(Math.max(0, y1 * 100 - 2)) + '%')
      label.setAttribute('fill', color)
      label.textContent = loc.person_id !== null ? `#${loc.person_id}` : `?${loc.global_track_id.slice(0, 6)}`
    }
  }

  return (
    <svg
      ref={svgRef}
      className="pointer-events-none absolute inset-0 h-full w-full"
      viewBox="0 0 1 1"
      preserveAspectRatio="none"
      aria-hidden="true"
    />
  )
}
