/**
 * Hand-written API contract types matching the FastAPI backend schemas.
 * Run `pnpm gen:types` (requires backend running on :8000) to regenerate
 * from the OpenAPI spec and replace this file with the generated version.
 */

// ─── Auth ─────────────────────────────────────────────────────────────────

export interface TokenRequest {
  username: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
}

/** Decoded JWT payload — client-side only, for routing decisions. */
export interface JwtPayload {
  sub: string
  role: 'guard' | 'manager' | 'admin'
  exp: number
}

// ─── Persons ──────────────────────────────────────────────────────────────

export interface PersonResponse {
  person_id: number
  name: string
  employee_id: string
  is_active: boolean
}

export interface PersonListResponse {
  items: PersonResponse[]
  total: number
  limit: number
  offset: number
}

// ─── Zones ────────────────────────────────────────────────────────────────

export interface ZoneResponse {
  zone_id: number
  name: string
  polygon: [number, number][] | null
  allowed_hours: string | null
  max_capacity: number | null
  loiter_threshold_s: number
  floor_plan_id: number | null
  is_active: boolean
}

export interface ZoneCreate {
  name: string
  polygon: [number, number][]
  allowed_hours?: string | null
  max_capacity?: number | null
  loiter_threshold_s?: number
  floor_plan_id?: number | null
}

export interface ZoneUpdate {
  name?: string
  polygon?: [number, number][]
  allowed_hours?: string | null
  max_capacity?: number | null
  loiter_threshold_s?: number
  floor_plan_id?: number | null
  is_active?: boolean
}

// ─── Alerts ───────────────────────────────────────────────────────────────

export type AlertSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
export type AlertState = 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED'
export type AlertType =
  | 'UNKNOWN_PERSON'
  | 'INTRUSION'
  | 'LOITERING'
  | 'VIOLENCE'
  | 'PPE_VIOLATION'
  | 'SYSTEM_CRITICAL'

export interface AlertResponse {
  alert_id: number
  alert_type: AlertType
  severity: AlertSeverity
  state: AlertState
  camera_id: number | null
  zone_id: number | null
  person_id: number | null
  triggered_at: string
  acknowledged_at: string | null
  resolved_at: string | null
  suppressed_by_window_id: number | null
  dedup_key: string | null
}

// ─── Cameras ──────────────────────────────────────────────────────────────

export type CapabilityTier = 'FULL' | 'MID' | 'LOW'
export type CameraStatus = 'online' | 'offline' | 'auth_failed' | 'maintenance'

export interface CameraResponse {
  camera_id: number
  name: string
  rtsp_url: string
  is_active: boolean
  capability_tier: CapabilityTier
  shutter_type: string
  profile_data: string | null
  profiled_at: string | null
  model_overrides: string | null
  worker_group: number | null
  recalibrate_required_at: string | null
}

// ─── Analytics ────────────────────────────────────────────────────────────────

export interface AnalyticsKpi {
  head_count_peak: number
  avg_dwell_minutes: number | null
  unknown_person_events: number
  camera_uptime_pct: number
}

export interface HeadCountPoint {
  date: string
  peak: number
  avg: number
}

export interface AlertCountByType {
  alert_type: AlertType
  count: number
}

export interface PersonProfile {
  person_id: number
  name: string
  employee_id: string
  is_active: boolean
  department: string | null
  last_seen_at: string | null
  last_seen_camera_id: number | null
  thumbnail_url: string | null
}

// ─── Forensic ─────────────────────────────────────────────────────────────────

export interface ForensicClip {
  global_track_id: string
  camera_id: number
  zone_id: number | null
  score: number
  triggered_at: string
  thumbnail_url: string | null
  clip_url: string | null
  duration_s: number | null
  alert_id: number | null
}

// ─── State snapshot ───────────────────────────────────────────────────────

export interface HeadCount {
  plant_total: number
  by_zone: Record<string, number>
  ts: string
}

export interface StateSnapshot {
  ts: string
  schema_version: string
  head_count: HeadCount
  active_alerts: AlertResponse[]
  cameras: CameraResponse[]
  degraded: Record<string, unknown> | null
}
