import type { Socket } from 'socket.io-client'
import { useLiveStore } from './store/liveStore'
import { queuePersonLocation } from './rafThrottle'
import type { AlertState, AlertSeverity, AlertType } from '@/shared/api/types'
import type { PersonLocation, LiveAlert } from './types'

interface AlertFiredPayload {
  alert_id: number
  alert_type: AlertType
  severity: AlertSeverity
  camera_id: number
  zone_id: number | null
  global_track_id: string | null
  snapshot_url: string | null
  ts: string
}

interface AlertStateChangedPayload {
  alert_id: number
  new_state: AlertState
  actor_user_id: number | null
  ts: string
}

interface TrackCorrectedPayload {
  global_track_id: string
  new_person_id: number
  ts: string
}

interface CameraSnapshotPayload {
  camera_id: number
  url: string
  ts: string
}

interface HeadCountPayload {
  plant_total: number
  by_zone: Record<string, number>
  ts: string
}

interface DegradedModePayload {
  enabled: boolean
  reason: string
}

export function attachSocketDispatch(socket: Socket): () => void {
  const store = () => useLiveStore.getState()

  const onPersonLocation = (loc: PersonLocation) => queuePersonLocation(loc)

  const onAlertFired = (p: AlertFiredPayload) => {
    const alert: LiveAlert = {
      alert_id: p.alert_id,
      alert_type: p.alert_type,
      severity: p.severity,
      state: 'OPEN',
      camera_id: p.camera_id,
      zone_id: p.zone_id,
      person_id: null,
      triggered_at: p.ts,
      acknowledged_at: null,
      resolved_at: null,
      suppressed_by_window_id: null,
      dedup_key: null,
      global_track_id: p.global_track_id,
      snapshot_url: p.snapshot_url,
    }
    store().applyAlertFired(alert)
  }

  const onAlertStateChanged = (p: AlertStateChangedPayload) => {
    store().applyAlertStateChanged(p.alert_id, p.new_state)
  }

  const onTrackCorrected = (p: TrackCorrectedPayload) => {
    store().applyTrackCorrected(p.global_track_id, p.new_person_id)
  }

  const onCameraSnapshot = (p: CameraSnapshotPayload) => {
    store().applyCameraSnapshot(p.camera_id, p.url)
  }

  const onHeadCount = (p: HeadCountPayload) => {
    store().applyHeadCount({
      total: p.plant_total,
      byZone: Object.fromEntries(
        Object.entries(p.by_zone).map(([k, v]) => [Number(k), v]),
      ),
    })
  }

  const onDegradedMode = (p: DegradedModePayload) => {
    useLiveStore.setState({
      degraded: p.enabled ? { connection: p.reason } : null,
    })
  }

  socket.on('person_location', onPersonLocation)
  socket.on('alert_fired', onAlertFired)
  socket.on('alert_state_changed', onAlertStateChanged)
  socket.on('track_corrected', onTrackCorrected)
  socket.on('camera_snapshot', onCameraSnapshot)
  socket.on('head_count', onHeadCount)
  socket.on('degraded_mode', onDegradedMode)

  return () => {
    socket.off('person_location', onPersonLocation)
    socket.off('alert_fired', onAlertFired)
    socket.off('alert_state_changed', onAlertStateChanged)
    socket.off('track_corrected', onTrackCorrected)
    socket.off('camera_snapshot', onCameraSnapshot)
    socket.off('head_count', onHeadCount)
    socket.off('degraded_mode', onDegradedMode)
  }
}
