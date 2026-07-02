import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { queuePersonLocation, flush, _resetThrottle } from './rafThrottle'
import { useLiveStore } from './store/liveStore'
import type { PersonLocation } from './types'

function makeLoc(trackId: string, x = 0): PersonLocation {
  return {
    global_track_id: trackId,
    person_id: null,
    camera_id: 1,
    bbox: [x, 0, x + 0.1, 0.1],
    floor_x: null,
    floor_y: null,
    ts: '2026-07-02T00:00:00',
  }
}

describe('rafThrottle — queuePersonLocation / flush', () => {
  let applyLocations: ReturnType<typeof vi.fn>

  beforeEach(() => {
    _resetThrottle()
    applyLocations = vi.fn()
    useLiveStore.setState({ applyLocations } as never)
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    useLiveStore.setState({ applyLocations: undefined } as never)
  })

  it('does not call applyLocations immediately on queue', () => {
    queuePersonLocation(makeLoc('track-1'))
    expect(applyLocations).not.toHaveBeenCalled()
  })

  it('calls applyLocations once on flush with all queued locations', () => {
    queuePersonLocation(makeLoc('track-1'))
    queuePersonLocation(makeLoc('track-2'))
    flush()
    expect(applyLocations).toHaveBeenCalledTimes(1)
    const locs = applyLocations.mock.calls[0][0] as PersonLocation[]
    expect(locs).toHaveLength(2)
  })

  it('last-write-wins for duplicate track IDs', () => {
    queuePersonLocation(makeLoc('track-1', 0.1))
    queuePersonLocation(makeLoc('track-1', 0.9))
    flush()
    const locs = applyLocations.mock.calls[0][0] as PersonLocation[]
    expect(locs).toHaveLength(1)
    expect(locs[0].bbox[0]).toBe(0.9)
  })

  it('clears pending after flush — second flush is a no-op', () => {
    queuePersonLocation(makeLoc('track-1'))
    flush()
    flush()
    expect(applyLocations).toHaveBeenCalledTimes(1)
  })

  it('does not call applyLocations on flush when queue is empty', () => {
    flush()
    expect(applyLocations).not.toHaveBeenCalled()
  })
})
