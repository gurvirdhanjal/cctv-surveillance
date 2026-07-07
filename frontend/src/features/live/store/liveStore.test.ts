import { describe, it, expect, beforeEach } from 'vitest'
import { useLiveStore } from './liveStore'
import type { StateSnapshot } from '@/shared/api/types'
import type { LiveAlert, PersonLocation } from '../types'

const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
})

const makeSnapshot = (overrides: Partial<StateSnapshot> = {}): StateSnapshot => ({
  ts: '2026-06-24T10:00:00Z',
  schema_version: '2',
  head_count: { plant_total: 5, by_zone: { '1': 3, '2': 2 }, ts: '2026-06-24T10:00:00Z' },
  active_alerts: [],
  cameras: [
    {
      camera_id: 1,
      name: 'Loading Bay',
      rtsp_url: 'rtsp://cam1',
      is_active: true,
      capability_tier: 'FULL',
      shutter_type: 'global',
      profile_data: null,
      profiled_at: null,
      model_overrides: null,
      worker_group: null,
      recalibrate_required_at: null,
    },
    {
      camera_id: 2,
      name: 'Exit Gate',
      rtsp_url: 'rtsp://cam2',
      is_active: false,
      capability_tier: 'MID',
      shutter_type: 'rolling',
      profile_data: null,
      profiled_at: null,
      model_overrides: null,
      worker_group: null,
      recalibrate_required_at: null,
    },
  ],
  degraded: null,
  ...overrides,
})

const makeAlert = (id: number, overrides: Partial<LiveAlert> = {}): LiveAlert => ({
  alert_id: id,
  alert_type: 'INTRUSION',
  severity: 'HIGH',
  state: 'OPEN',
  camera_id: 1,
  zone_id: null,
  person_id: null,
  triggered_at: '2026-06-24T10:00:00Z',
  acknowledged_at: null,
  resolved_at: null,
  suppressed_by_window_id: null,
  dedup_key: null,
  global_track_id: null,
  snapshot_url: null,
  ...overrides,
})

describe('liveStore', () => {
  describe('reset', () => {
    it('populates cameras from snapshot, deriving status from is_active', () => {
      useLiveStore.getState().reset(makeSnapshot())
      const { cameras } = useLiveStore.getState()
      expect(cameras).toHaveLength(2)
      expect(cameras[0]).toMatchObject({ camera_id: 1, name: 'Loading Bay', status: 'online' })
      expect(cameras[1]).toMatchObject({ camera_id: 2, name: 'Exit Gate', status: 'offline' })
    })

    it('populates headCount from snapshot', () => {
      useLiveStore.getState().reset(makeSnapshot())
      const { headCount } = useLiveStore.getState()
      expect(headCount.total).toBe(5)
      expect(headCount.byZone[1]).toBe(3)
      expect(headCount.byZone[2]).toBe(2)
    })

    it('seeds alerts from snapshot, adding null live-alert fields', () => {
      const snap = makeSnapshot({
        active_alerts: [
          {
            alert_id: 42,
            alert_type: 'VIOLENCE',
            severity: 'CRITICAL',
            state: 'OPEN',
            camera_id: 1,
            zone_id: null,
            person_id: null,
            triggered_at: '2026-06-24T09:00:00Z',
            acknowledged_at: null,
            resolved_at: null,
            suppressed_by_window_id: null,
            dedup_key: null,
          },
        ],
      })
      useLiveStore.getState().reset(snap)
      const { alerts } = useLiveStore.getState()
      expect(alerts).toHaveLength(1)
      expect(alerts[0].alert_id).toBe(42)
      expect(alerts[0].global_track_id).toBeNull()
    })

    it('clears trackedPersons on reset', () => {
      // Put something in trackedPersons first
      useLiveStore.getState().applyLocations([
        { global_track_id: 'gid-1', person_id: null, camera_id: 1, bbox: [0, 0, 0.5, 0.5], floor_x: null, floor_y: null, ts: 't' },
      ])
      useLiveStore.getState().reset(makeSnapshot())
      expect(useLiveStore.getState().trackedPersons.size).toBe(0)
    })

    it('sets degraded from snapshot when present', () => {
      useLiveStore.getState().reset(makeSnapshot({ degraded: { connection: 'lost' } }))
      expect(useLiveStore.getState().degraded).toEqual({ connection: 'lost' })
    })
  })

  describe('applyLocations', () => {
    it('adds new locations to trackedPersons', () => {
      const loc: PersonLocation = {
        global_track_id: 'gid-1',
        person_id: 10,
        camera_id: 1,
        bbox: [0.1, 0.2, 0.3, 0.4],
        floor_x: 10,
        floor_y: 20,
        ts: '2026-06-24T10:00:00Z',
      }
      useLiveStore.getState().applyLocations([loc])
      expect(useLiveStore.getState().trackedPersons.get('gid-1')).toEqual(loc)
    })

    it('last-write-wins for duplicate track IDs', () => {
      const loc1: PersonLocation = {
        global_track_id: 'gid-1', person_id: null, camera_id: 1,
        bbox: [0, 0, 0.1, 0.1], floor_x: 1, floor_y: 2, ts: 't1',
      }
      const loc2: PersonLocation = {
        global_track_id: 'gid-1', person_id: null, camera_id: 1,
        bbox: [0.5, 0.5, 0.9, 0.9], floor_x: 5, floor_y: 6, ts: 't2',
      }
      useLiveStore.getState().applyLocations([loc1, loc2])
      expect(useLiveStore.getState().trackedPersons.get('gid-1')?.floor_x).toBe(5)
    })

    it('preserves existing entries for other tracks', () => {
      useLiveStore.getState().applyLocations([
        { global_track_id: 'gid-A', person_id: null, camera_id: 1, bbox: [0,0,1,1], floor_x: null, floor_y: null, ts: 't' },
      ])
      useLiveStore.getState().applyLocations([
        { global_track_id: 'gid-B', person_id: null, camera_id: 2, bbox: [0,0,1,1], floor_x: null, floor_y: null, ts: 't' },
      ])
      expect(useLiveStore.getState().trackedPersons.size).toBe(2)
    })
  })

  describe('applyAlertFired', () => {
    it('prepends new alert to the alerts list', () => {
      useLiveStore.getState().applyAlertFired(makeAlert(1))
      useLiveStore.getState().applyAlertFired(makeAlert(2))
      const { alerts } = useLiveStore.getState()
      expect(alerts[0].alert_id).toBe(2)
      expect(alerts[1].alert_id).toBe(1)
    })
  })

  describe('applyAlertStateChanged', () => {
    it('updates the state of the matching alert', () => {
      useLiveStore.getState().applyAlertFired(makeAlert(10))
      useLiveStore.getState().applyAlertStateChanged(10, 'ACKNOWLEDGED')
      expect(useLiveStore.getState().alerts[0].state).toBe('ACKNOWLEDGED')
    })

    it('leaves other alerts unchanged', () => {
      useLiveStore.getState().applyAlertFired(makeAlert(10))
      useLiveStore.getState().applyAlertFired(makeAlert(11))
      useLiveStore.getState().applyAlertStateChanged(10, 'RESOLVED')
      expect(useLiveStore.getState().alerts.find((a) => a.alert_id === 11)?.state).toBe('OPEN')
    })
  })

  describe('setFocusedCamera', () => {
    it('updates focusedCameraId', () => {
      useLiveStore.getState().setFocusedCamera(3)
      expect(useLiveStore.getState().focusedCameraId).toBe(3)
    })

    it('accepts null to clear', () => {
      useLiveStore.getState().setFocusedCamera(3)
      useLiveStore.getState().setFocusedCamera(null)
      expect(useLiveStore.getState().focusedCameraId).toBeNull()
    })
  })

  describe('setFollowedTrack', () => {
    it('updates followedTrackId', () => {
      useLiveStore.getState().setFollowedTrack('gid-42')
      expect(useLiveStore.getState().followedTrackId).toBe('gid-42')
    })

    it('accepts null to clear', () => {
      useLiveStore.getState().setFollowedTrack('gid-42')
      useLiveStore.getState().setFollowedTrack(null)
      expect(useLiveStore.getState().followedTrackId).toBeNull()
    })
  })

  describe('setGridLayout', () => {
    it('persists the layout value', () => {
      useLiveStore.getState().setGridLayout(9)
      expect(useLiveStore.getState().gridLayout).toBe(9)
    })

    it('can switch between valid values', () => {
      useLiveStore.getState().setGridLayout(16)
      expect(useLiveStore.getState().gridLayout).toBe(16)
      useLiveStore.getState().setGridLayout(1)
      expect(useLiveStore.getState().gridLayout).toBe(1)
    })
  })

  describe('setWsStatus', () => {
    it('transitions from offline to connected', () => {
      useLiveStore.getState().setWsStatus('connected')
      expect(useLiveStore.getState().wsStatus).toBe('connected')
    })

    it('transitions through reconnecting', () => {
      useLiveStore.getState().setWsStatus('reconnecting')
      expect(useLiveStore.getState().wsStatus).toBe('reconnecting')
    })
  })

  describe('addBookmark / removeBookmark', () => {
    it('addBookmark appends a new bookmark', () => {
      useLiveStore.getState().addBookmark({ cameraId: 1, tsMs: 1000, label: 'test' })
      useLiveStore.getState().addBookmark({ cameraId: 2, tsMs: 2000 })
      expect(useLiveStore.getState().bookmarks).toHaveLength(2)
    })

    it('removeBookmark removes matching entry', () => {
      useLiveStore.getState().addBookmark({ cameraId: 1, tsMs: 1000 })
      useLiveStore.getState().addBookmark({ cameraId: 2, tsMs: 2000 })
      useLiveStore.getState().removeBookmark(1, 1000)
      const { bookmarks } = useLiveStore.getState()
      expect(bookmarks).toHaveLength(1)
      expect(bookmarks[0].cameraId).toBe(2)
    })
  })

  describe('upsertAlert', () => {
    it('inserts a new alert when id not present', () => {
      useLiveStore.getState().upsertAlert(makeAlert(5))
      expect(useLiveStore.getState().alerts).toHaveLength(1)
    })

    it('updates existing alert (dedups by id)', () => {
      useLiveStore.getState().upsertAlert(makeAlert(5))
      useLiveStore.getState().upsertAlert(makeAlert(5, { severity: 'CRITICAL' }))
      const { alerts } = useLiveStore.getState()
      expect(alerts).toHaveLength(1)
      expect(alerts[0].severity).toBe('CRITICAL')
    })

    it('keeps list sorted by severity then recency', () => {
      useLiveStore.getState().upsertAlert(makeAlert(1, { severity: 'LOW', triggered_at: '2026-07-07T10:00:00Z' }))
      useLiveStore.getState().upsertAlert(makeAlert(2, { severity: 'CRITICAL', triggered_at: '2026-07-07T09:00:00Z' }))
      const { alerts } = useLiveStore.getState()
      expect(alerts[0].severity).toBe('CRITICAL')
      expect(alerts[1].severity).toBe('LOW')
    })
  })

  describe('acknowledgeAlert / resolveAlert', () => {
    it('acknowledgeAlert sets state to ACKNOWLEDGED', () => {
      useLiveStore.getState().upsertAlert(makeAlert(7))
      useLiveStore.getState().acknowledgeAlert(7)
      expect(useLiveStore.getState().alerts[0].state).toBe('ACKNOWLEDGED')
    })

    it('resolveAlert sets state to RESOLVED', () => {
      useLiveStore.getState().upsertAlert(makeAlert(8))
      useLiveStore.getState().resolveAlert(8)
      expect(useLiveStore.getState().alerts[0].state).toBe('RESOLVED')
    })

    it('leaves other alerts unchanged', () => {
      useLiveStore.getState().upsertAlert(makeAlert(10))
      useLiveStore.getState().upsertAlert(makeAlert(11))
      useLiveStore.getState().acknowledgeAlert(10)
      expect(useLiveStore.getState().alerts.find((a) => a.alert_id === 11)?.state).toBe('OPEN')
    })
  })
})
