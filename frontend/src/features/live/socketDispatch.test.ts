import { vi, describe, it, expect, beforeEach } from 'vitest'
import { attachSocketDispatch } from './socketDispatch'
import { useLiveStore } from './store/liveStore'

vi.mock('./rafThrottle', () => ({
  queuePersonLocation: vi.fn(),
}))

import { queuePersonLocation } from './rafThrottle'

function makeSocket() {
  const handlers: Record<string, ((...args: unknown[]) => void)[]> = {}
  return {
    on: vi.fn((event: string, handler: (...args: unknown[]) => void) => {
      ;(handlers[event] ??= []).push(handler)
    }),
    off: vi.fn((event: string, handler: (...args: unknown[]) => void) => {
      handlers[event] = (handlers[event] ?? []).filter((h) => h !== handler)
    }),
    emit: (event: string, ...args: unknown[]) => {
      handlers[event]?.forEach((h) => h(...args))
    },
  }
}

describe('socketDispatch', () => {
  let socket: ReturnType<typeof makeSocket>
  let detach: () => void

  beforeEach(() => {
    socket = makeSocket()
    useLiveStore.setState({
      alerts: [],
      trackedPersons: new Map(),
      cameras: [],
      headCount: { total: 0, byZone: {} },
      degraded: null,
      applyAlertFired: useLiveStore.getState().applyAlertFired,
      applyAlertStateChanged: useLiveStore.getState().applyAlertStateChanged,
      applyHeadCount: useLiveStore.getState().applyHeadCount,
      applyCameraSnapshot: useLiveStore.getState().applyCameraSnapshot,
      applyTrackCorrected: useLiveStore.getState().applyTrackCorrected,
      applyLocations: useLiveStore.getState().applyLocations,
    })
    vi.mocked(queuePersonLocation).mockClear()
    detach = attachSocketDispatch(socket as never)
  })

  it('person_location routes to queuePersonLocation', () => {
    const loc = { global_track_id: 'g1', person_id: null, camera_id: 1, bbox: [0, 0, 0.1, 0.1], floor_x: null, floor_y: null, ts: 't' }
    socket.emit('person_location', loc)
    expect(queuePersonLocation).toHaveBeenCalledWith(loc)
  })

  it('alert_fired prepends alert to store', () => {
    socket.emit('alert_fired', {
      alert_id: 99,
      alert_type: 'INTRUSION',
      severity: 'HIGH',
      camera_id: 1,
      zone_id: null,
      global_track_id: 'g1',
      snapshot_url: null,
      ts: '2026-07-02T00:00:00',
    })
    const alerts = useLiveStore.getState().alerts
    expect(alerts).toHaveLength(1)
    expect(alerts[0].alert_id).toBe(99)
    expect(alerts[0].state).toBe('OPEN')
  })

  it('alert_state_changed updates alert state in store', () => {
    useLiveStore.setState({
      alerts: [
        { alert_id: 5, state: 'OPEN', alert_type: 'INTRUSION', severity: 'HIGH', camera_id: 1, zone_id: null, person_id: null, triggered_at: 't', acknowledged_at: null, resolved_at: null, suppressed_by_window_id: null, dedup_key: null, global_track_id: null, snapshot_url: null },
      ],
    })
    socket.emit('alert_state_changed', { alert_id: 5, new_state: 'ACKNOWLEDGED', actor_user_id: null, ts: 't' })
    expect(useLiveStore.getState().alerts[0].state).toBe('ACKNOWLEDGED')
  })

  it('head_count updates headCount in store', () => {
    socket.emit('head_count', { plant_total: 42, by_zone: { '1': 10, '2': 32 }, ts: 't' })
    const hc = useLiveStore.getState().headCount
    expect(hc.total).toBe(42)
    expect(hc.byZone[1]).toBe(10)
    expect(hc.byZone[2]).toBe(32)
  })

  it('camera_snapshot updates camera snapshotUrl in store', () => {
    useLiveStore.setState({
      cameras: [{ camera_id: 3, name: 'C3', capability_tier: 'FULL', status: 'online', is_active: true, snapshotUrl: null }],
    })
    socket.emit('camera_snapshot', { camera_id: 3, url: '/media/snap.jpg', ts: 't' })
    expect(useLiveStore.getState().cameras[0].snapshotUrl).toBe('/media/snap.jpg')
  })

  it('track_corrected updates person_id in trackedPersons', () => {
    useLiveStore.setState({
      trackedPersons: new Map([['g1', { global_track_id: 'g1', person_id: null, camera_id: 1, bbox: [0, 0, 0.1, 0.1], floor_x: null, floor_y: null, ts: 't' }]]),
    })
    socket.emit('track_corrected', { global_track_id: 'g1', new_person_id: 7, ts: 't' })
    expect(useLiveStore.getState().trackedPersons.get('g1')?.person_id).toBe(7)
  })

  it('degraded_mode enabled sets degraded in store', () => {
    socket.emit('degraded_mode', { enabled: true, reason: 'Redis lag' })
    expect(useLiveStore.getState().degraded).toEqual({ connection: 'Redis lag' })
  })

  it('degraded_mode disabled clears degraded in store', () => {
    useLiveStore.setState({ degraded: { connection: 'lost' } })
    socket.emit('degraded_mode', { enabled: false, reason: '' })
    expect(useLiveStore.getState().degraded).toBeNull()
  })

  it('detach removes all event handlers', () => {
    detach()
    expect(socket.off).toHaveBeenCalledWith('person_location', expect.any(Function))
    expect(socket.off).toHaveBeenCalledWith('alert_fired', expect.any(Function))
    expect(socket.off).toHaveBeenCalledWith('head_count', expect.any(Function))
  })
})
