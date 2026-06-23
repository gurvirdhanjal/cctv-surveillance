import type { ZoneResponse } from '@/shared/api/types'

interface ZoneDwellData {
  zone_id: number
  dwell_minutes: number
}

interface HeatmapOverlayProps {
  zones: ZoneResponse[]
  dwellData: ZoneDwellData[]
  imageWidth: number
  imageHeight: number
  maxDwell?: number
}

function intensityColor(ratio: number): string {
  const r = Math.round(255 * Math.min(1, ratio * 2))
  const g = Math.round(255 * Math.max(0, 1 - ratio * 2))
  const b = Math.round(200 * (1 - ratio))
  return `rgba(${r},${g},${b},0.45)`
}

export function HeatmapOverlay({
  zones,
  dwellData,
  imageWidth,
  imageHeight,
  maxDwell,
}: HeatmapOverlayProps) {
  const dwellMap = new Map(dwellData.map((d) => [d.zone_id, d.dwell_minutes]))
  const max = maxDwell ?? Math.max(1, ...dwellData.map((d) => d.dwell_minutes))

  return (
    <svg
      viewBox={`0 0 ${imageWidth} ${imageHeight}`}
      className="absolute inset-0 h-full w-full"
      aria-label="Heatmap overlay"
      role="img"
    >
      {zones.map((zone) => {
        if (!zone.polygon || zone.polygon.length < 3) return null
        const dwell = dwellMap.get(zone.zone_id) ?? 0
        const ratio = dwell / max
        const points = zone.polygon.map(([x, y]) => `${x},${y}`).join(' ')
        return (
          <polygon
            key={zone.zone_id}
            points={points}
            fill={intensityColor(ratio)}
            stroke="var(--border-strong)"
            strokeWidth={1}
            data-zone-id={zone.zone_id}
            aria-label={zone.name}
          />
        )
      })}
    </svg>
  )
}
