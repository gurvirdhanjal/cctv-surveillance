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

// ─── Admin — cameras ──────────────────────────────────────────────────────

export interface CameraCreate {
  name: string
  rtsp_url: string
  capability_tier?: CapabilityTier
  shutter_type?: 'rolling' | 'global' | 'unknown'
  worker_group?: number | null
}

export interface ProfileData {
  resolution_w: number | null
  resolution_h: number | null
  fps_measured: number | null
  focus_score: number | null
  frame_drop_rate: number | null
  brightness_mean: number | null
  shutter_suggestion: 'rolling' | 'global' | 'unknown' | null
  shutter_confidence: number | null
  suggested_tier: CapabilityTier | null
  tier_reason: string | null
}

export interface ProfileResponse {
  camera_id: number
  profile_data: ProfileData | null
  profiled_at: string | null
  capability_tier: string
  shutter_type: string
  tier_reason: string | null
}

export interface ResolvedSettingItem {
  value: unknown
  source: string
}

export interface ResolvedConfigResponse {
  camera_id: number
  settings: Record<string, ResolvedSettingItem>
}

// ─── Admin — maintenance ───────────────────────────────────────────────────

export interface MaintenanceWindow {
  window_id: number
  name: string
  scope_type: string
  scope_id: number
  schedule_type: string
  starts_at: string | null
  ends_at: string | null
  cron_expr: string | null
  duration_minutes: number | null
  suppress_alert_types: string | null
  is_active: boolean
  reason: string | null
}

export interface MaintenanceWindowCreate {
  name: string
  scope_type: string
  scope_id: number
  schedule_type: string
  starts_at?: string | null
  ends_at?: string | null
  cron_expr?: string | null
  duration_minutes?: number | null
  suppress_alert_types?: string | null
  reason?: string | null
}

export interface CalendarSlot {
  window_id: number
  name: string
  scope_type: string
  scope_id: number
  starts_at: string
  ends_at: string
  is_recurring: boolean
  suppress_alert_types: string[] | null
}

// ─── Admin — anomaly detectors ────────────────────────────────────────────

export interface AnomalyDetector {
  detector_id: number
  alert_type: string
  class_path: string
  is_enabled: boolean
  config_json: string | null
  model_version: string | null
}

// ─── Admin — alert routing ────────────────────────────────────────────────

export interface AlertRoutingRule {
  routing_id: number
  alert_type: string | null
  severity: string | null
  zone_id: number | null
  channel: string
  target: string
  is_active: boolean
}

export interface AlertRoutingCreate {
  alert_type?: string | null
  severity?: string | null
  zone_id?: number | null
  channel: string
  target: string
}

// ─── Admin — audit ────────────────────────────────────────────────────────

export interface AuditVerifyResponse {
  rows_checked: number
  broken_chain_at: string | null
}

export interface AuditLogEntry {
  log_id: number
  event_type: string
  actor_user_id: number | null
  actor_role: string | null
  subject_table: string | null
  subject_id: string | null
  detail: string | null
  created_at: string
  row_hash: string
}

// ─── Admin — health ───────────────────────────────────────────────────────

export interface HealthResponse {
  status: string
  version: string
}

export interface ReadinessResponse {
  db: 'ok' | 'fail'
  redis: 'ok' | 'fail'
}

// ─── Admin — users ────────────────────────────────────────────────────────

export interface UserResponse {
  user_id: number
  username: string
  role: 'guard' | 'manager' | 'admin'
  is_active: boolean
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
