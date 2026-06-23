import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { FloorPlanMarker } from './FloorPlan'

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="map-container">{children}</div>
  ),
  ImageOverlay: ({ url }: { url: string }) => (
    <img data-testid="floor-plan-image" src={url} alt="" />
  ),
  Marker: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="floor-plan-marker">{children}</div>
  ),
  Popup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('leaflet', () => ({
  CRS: { Simple: {} },
  divIcon: vi.fn(() => ({ html: '', iconSize: [10, 10] })),
}))

vi.mock('leaflet/dist/leaflet.css', () => ({}))

const { FloorPlan } = await import('./FloorPlan')

const BOUNDS: [[number, number], [number, number]] = [
  [0, 0],
  [100, 100],
]

describe('FloorPlan', () => {
  it('renders the map container', () => {
    render(<FloorPlan imageUrl="/floor.png" bounds={BOUNDS} />)
    expect(screen.getByTestId('map-container')).toBeInTheDocument()
  })

  it('mounts the image overlay', () => {
    render(<FloorPlan imageUrl="/floor.png" bounds={BOUNDS} />)
    expect(screen.getByTestId('floor-plan-image')).toHaveAttribute('src', '/floor.png')
  })

  it('renders a marker for each item', () => {
    const markers: FloorPlanMarker[] = [
      { id: 'a', position: [10, 20] },
      { id: 'b', position: [50, 60] },
    ]
    render(<FloorPlan imageUrl="/floor.png" bounds={BOUNDS} markers={markers} />)
    expect(screen.getAllByTestId('floor-plan-marker')).toHaveLength(2)
  })

  it('has accessible label', () => {
    render(<FloorPlan imageUrl="/floor.png" bounds={BOUNDS} />)
    expect(screen.getByLabelText('Floor plan')).toBeInTheDocument()
  })
})
