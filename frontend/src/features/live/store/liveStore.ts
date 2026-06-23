import { create } from 'zustand'
import type { AlertState, StateSnapshot } from '@/shared/api/types'
import type { CameraState, LiveAlert, PersonLocation } from '../types'

interface HeadCountState {
  total: number
  byZone: Record<number, number>
}

interface LiveState {
  cameras: CameraState[]
  focusedCameraId: number | null
  followedTrackId: string | null
  alerts: LiveAlert[]
  trackedPersons: Map<string, PersonLocation>
  headCount: HeadCountState
  degraded: { connection?: string; redis?: string } | null

  reset: (snapshot: StateSnapshot) => void
  applyLocations: (locs: PersonLocation[]) => void
  applyAlertFired: (alert: LiveAlert) => void
  applyAlertStateChanged: (id: number, state: AlertState) => void
  setFocusedCamera: (id: number | null) => void
  setFollowedTrack: (id: string | null) => void
}

export const useLiveStore = create<LiveState>((set) => ({
  cameras: [],
  focusedCameraId: null,
  followedTrackId: null,
  alerts: [],
  trackedPersons: new Map(),
  headCount: { total: 0, byZone: {} },
  degraded: null,

  reset: (snapshot) =>
    set({
      cameras: snapshot.cameras.map((c) => ({
        camera_id: c.camera_id,
        name: c.name,
        capability_tier: c.capability_tier,
        status: c.is_active ? 'online' : 'offline',
        is_active: c.is_active,
        snapshotUrl: null,
      })),
      alerts: snapshot.active_alerts.map((a) => ({
        ...a,
        global_track_id: null,
        snapshot_url: null,
      })),
      headCount: {
        total: snapshot.head_count.plant_total,
        byZone: Object.fromEntries(
          Object.entries(snapshot.head_count.by_zone).map(([k, v]) => [Number(k), v]),
        ),
      },
      degraded: snapshot.degraded
        ? (snapshot.degraded as { connection?: string; redis?: string })
        : null,
      trackedPersons: new Map(),
    }),

  applyLocations: (locs) =>
    set((state) => {
      const next = new Map(state.trackedPersons)
      for (const loc of locs) {
        next.set(loc.global_track_id, loc)
      }
      return { trackedPersons: next }
    }),

  applyAlertFired: (alert) =>
    set((state) => ({ alerts: [alert, ...state.alerts] })),

  applyAlertStateChanged: (id, newState) =>
    set((state) => ({
      alerts: state.alerts.map((a) =>
        a.alert_id === id ? { ...a, state: newState } : a,
      ),
    })),

  setFocusedCamera: (id) => set({ focusedCameraId: id }),
  setFollowedTrack: (id) => set({ followedTrackId: id }),
}))
