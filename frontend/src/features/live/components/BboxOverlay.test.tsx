import { describe, it, expect, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { BboxOverlay } from './BboxOverlay'
import { useLiveStore } from '../store/liveStore'
import type { PersonLocation } from '../types'

const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
})

function addLoc(overrides: Partial<PersonLocation> = {}) {
  const loc: PersonLocation = {
    global_track_id: 'gid-1',
    person_id: null,
    camera_id: 1,
    bbox: [0.1, 0.2, 0.4, 0.6],
    floor_x: null,
    floor_y: null,
    ts: '2026-06-24T10:00:00Z',
    ...overrides,
  }
  useLiveStore.getState().applyLocations([loc])
  return loc
}

describe('BboxOverlay', () => {
  it('renders an SVG element', () => {
    const { container } = render(<BboxOverlay cameraId={1} />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders a rect for a tracked person on the camera', () => {
    addLoc({ camera_id: 1 })
    const { container } = render(<BboxOverlay cameraId={1} />)
    expect(container.querySelectorAll('rect')).toHaveLength(1)
  })

  it('uses red dashed stroke for unknown person', () => {
    addLoc({ person_id: null, camera_id: 1 })
    const { container } = render(<BboxOverlay cameraId={1} />)
    const rect = container.querySelector('rect')
    expect(rect?.getAttribute('stroke')).toBe('#dc2626')
    expect(rect?.getAttribute('stroke-dasharray')).toBeTruthy()
  })

  it('uses solid brand stroke for known person', () => {
    addLoc({ person_id: 10, camera_id: 1 })
    const { container } = render(<BboxOverlay cameraId={1} />)
    const rect = container.querySelector('rect')
    expect(rect?.getAttribute('stroke')).toBe('#2b6cb0')
    expect(rect?.getAttribute('stroke-dasharray')).toBeFalsy()
  })

  it('does not render boxes for other cameras', () => {
    addLoc({ camera_id: 2 })
    const { container } = render(<BboxOverlay cameraId={1} />)
    expect(container.querySelectorAll('rect')).toHaveLength(0)
  })

  it('throttle batching: renders all locations applied in one batch', () => {
    useLiveStore.getState().applyLocations([
      { global_track_id: 'a', person_id: null, camera_id: 1, bbox: [0,0,0.1,0.1], floor_x: null, floor_y: null, ts: 't' },
      { global_track_id: 'b', person_id: null, camera_id: 1, bbox: [0.5,0.5,0.9,0.9], floor_x: null, floor_y: null, ts: 't' },
    ])
    const { container } = render(<BboxOverlay cameraId={1} />)
    expect(container.querySelectorAll('rect')).toHaveLength(2)
  })
})
