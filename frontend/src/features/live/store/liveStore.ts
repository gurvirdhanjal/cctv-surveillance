import { create } from 'zustand'
import type { AlertState, StateSnapshot } from '@/shared/api/types'
import type { CameraState, LiveAlert, PersonLocation } from '../types'

interface HeadCountState {
  total: number
  byZone: Record<number, number>
}

export interface LiveBookmark {
  cameraId: number
  tsMs: number
  label?: string
}

export type WsStatus = 'connected' | 'reconnecting' | 'offline'

const SEVERITY_ORDER: Record<string, number> = {
  CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3,
}

interface LiveState {
  cameras: CameraState[]
  focusedCameraId: number | null
  selectedCameraId: number | null
  followedTrackId: string | null
  alerts: LiveAlert[]
  trackedPersons: Map<string, PersonLocation>
  headCount: HeadCountState
  degraded: { connection?: string; redis?: string } | null
  gridLayout: 1 | 4 | 9 | 16
  wsStatus: WsStatus
  bookmarks: LiveBookmark[]
  floorPlanVisible: boolean
  gpuPct: number

  reset: (snapshot: StateSnapshot) => void
  applyLocations: (locs: PersonLocation[]) => void
  applyAlertFired: (alert: LiveAlert) => void
  applyAlertStateChanged: (id: number, state: AlertState) => void
  applyHeadCount: (hc: HeadCountState) => void
  applyCameraSnapshot: (cameraId: number, url: string) => void
  applyTrackCorrected: (globalTrackId: string, personId: number) => void
  setFocusedCamera: (id: number | null) => void
  setSelectedCamera: (id: number | null) => void
  setFollowedTrack: (id: string | null) => void
  setGridLayout: (layout: 1 | 4 | 9 | 16) => void
  setWsStatus: (status: WsStatus) => void
  toggleFloorPlan: () => void
  addBookmark: (bookmark: LiveBookmark) => void
  removeBookmark: (cameraId: number, tsMs: number) => void
  upsertAlert: (alert: LiveAlert) => void
  acknowledgeAlert: (id: number) => void
  resolveAlert: (id: number) => void
  setGpuPct: (pct: number) => void
}

export const useLiveStore = create<LiveState>((set) => ({
  cameras: [],
  focusedCameraId: null,
  selectedCameraId: null,
  followedTrackId: null,
  alerts: [],
  trackedPersons: new Map(),
  headCount: { total: 0, byZone: {} },
  degraded: null,
  gridLayout: 1,
  wsStatus: 'offline',
  bookmarks: [],
  floorPlanVisible: false,
  gpuPct: 0,

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

  applyHeadCount: (hc) => set({ headCount: hc }),

  applyCameraSnapshot: (cameraId, url) =>
    set((state) => ({
      cameras: state.cameras.map((c) =>
        c.camera_id === cameraId ? { ...c, snapshotUrl: url } : c,
      ),
    })),

  applyTrackCorrected: (globalTrackId, personId) =>
    set((state) => {
      const next = new Map(state.trackedPersons)
      const existing = next.get(globalTrackId)
      if (existing) next.set(globalTrackId, { ...existing, person_id: personId })
      return { trackedPersons: next }
    }),

  setFocusedCamera: (id) => set({ focusedCameraId: id }),
  setSelectedCamera: (id) => set({ selectedCameraId: id }),
  setFollowedTrack: (id) => set({ followedTrackId: id }),
  setGridLayout: (layout) => set({ gridLayout: layout }),
  setWsStatus: (status) => set({ wsStatus: status }),
  toggleFloorPlan: () => set((s) => ({ floorPlanVisible: !s.floorPlanVisible })),
  setGpuPct: (pct) => set({ gpuPct: pct }),

  addBookmark: (bookmark) =>
    set((s) => ({ bookmarks: [...s.bookmarks, bookmark] })),

  removeBookmark: (cameraId, tsMs) =>
    set((s) => ({
      bookmarks: s.bookmarks.filter((b) => !(b.cameraId === cameraId && b.tsMs === tsMs)),
    })),

  upsertAlert: (alert) =>
    set((s) => {
      const existing = s.alerts.findIndex((a) => a.alert_id === alert.alert_id)
      const next = existing >= 0
        ? s.alerts.map((a) => (a.alert_id === alert.alert_id ? alert : a))
        : [alert, ...s.alerts]
      return {
        alerts: [...next].sort((a, b) => {
          const sd = (SEVERITY_ORDER[a.severity] ?? 99) - (SEVERITY_ORDER[b.severity] ?? 99)
          return sd !== 0 ? sd : new Date(b.triggered_at).getTime() - new Date(a.triggered_at).getTime()
        }),
      }
    }),

  acknowledgeAlert: (id) =>
    set((s) => ({
      alerts: s.alerts.map((a) =>
        a.alert_id === id ? { ...a, state: 'ACKNOWLEDGED' as AlertState } : a,
      ),
    })),

  resolveAlert: (id) =>
    set((s) => ({
      alerts: s.alerts.map((a) =>
        a.alert_id === id ? { ...a, state: 'RESOLVED' as AlertState } : a,
      ),
    })),
}))
