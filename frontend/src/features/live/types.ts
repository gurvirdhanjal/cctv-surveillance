import type { AlertResponse } from '@/shared/api/types'

export type CameraStatus = 'online' | 'offline' | 'auth_failed' | 'maintenance'

export interface CameraState {
  camera_id: number
  name: string
  capability_tier: 'FULL' | 'MID' | 'LOW'
  status: CameraStatus
  is_active: boolean
  snapshotUrl: string | null
  // §Q hierarchy — null = use fallback label
  site_name?: string | null
  building_name?: string | null
  floor_name?: string | null
}

export interface PersonLocation {
  global_track_id: string
  person_id: number | null
  camera_id: number
  /** Normalised [x1, y1, x2, y2] in 0–1 range relative to frame size. */
  bbox: [number, number, number, number]
  floor_x: number | null
  floor_y: number | null
  ts: string
}

export interface LiveAlert extends AlertResponse {
  /** Set from socket `alert_fired` event; null for REST-seeded alerts. */
  global_track_id: string | null
  snapshot_url: string | null
  /** ISO deadline for operator SLA countdown; null = no SLA configured. */
  sla_deadline?: string | null
}
