import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { HeatmapOverlay } from './HeatmapOverlay'
import type { ZoneResponse } from '@/shared/api/types'

const zones: ZoneResponse[] = [
  {
    zone_id: 1,
    name: 'Entrance',
    polygon: [
      [0, 0],
      [100, 0],
      [100, 80],
      [0, 80],
    ],
    allowed_hours: null,
    max_capacity: null,
    loiter_threshold_s: 60,
    floor_plan_id: null,
    is_active: true,
  },
  {
    zone_id: 2,
    name: 'Assembly',
    polygon: [
      [100, 0],
      [200, 0],
      [200, 80],
      [100, 80],
    ],
    allowed_hours: null,
    max_capacity: null,
    loiter_threshold_s: 60,
    floor_plan_id: null,
    is_active: true,
  },
]

describe('HeatmapOverlay', () => {
  it('renders svg container with accessible label', () => {
    render(<HeatmapOverlay zones={zones} dwellData={[]} imageWidth={300} imageHeight={200} />)
    expect(screen.getByRole('img', { name: 'Heatmap overlay' })).toBeInTheDocument()
  })

  it('renders a polygon for each zone with polygon data', () => {
    render(
      <HeatmapOverlay
        zones={zones}
        dwellData={[
          { zone_id: 1, dwell_minutes: 30 },
          { zone_id: 2, dwell_minutes: 10 },
        ]}
        imageWidth={300}
        imageHeight={200}
      />,
    )
    expect(document.querySelectorAll('polygon')).toHaveLength(2)
  })

  it('assigns zone name as aria-label to each polygon', () => {
    render(<HeatmapOverlay zones={zones} dwellData={[]} imageWidth={300} imageHeight={200} />)
    expect(document.querySelector('[aria-label="Entrance"]')).toBeInTheDocument()
    expect(document.querySelector('[aria-label="Assembly"]')).toBeInTheDocument()
  })

  it('skips zones without polygon', () => {
    const noPolyZones: ZoneResponse[] = [{ ...zones[0], polygon: null }, zones[1]]
    render(<HeatmapOverlay zones={noPolyZones} dwellData={[]} imageWidth={300} imageHeight={200} />)
    expect(document.querySelectorAll('polygon')).toHaveLength(1)
  })

  it('skips zones with fewer than 3 polygon points', () => {
    const shortPolyZones: ZoneResponse[] = [
      { ...zones[0], polygon: [[0, 0], [100, 0]] },
      zones[1],
    ]
    render(
      <HeatmapOverlay zones={shortPolyZones} dwellData={[]} imageWidth={300} imageHeight={200} />,
    )
    expect(document.querySelectorAll('polygon')).toHaveLength(1)
  })
})
