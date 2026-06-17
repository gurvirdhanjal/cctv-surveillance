# VMS Database Schema

_Canonical reference. Source of truth: `vms/db/models.py`. Updated whenever a migration lands._
_PostgreSQL 16 + pgvector. All timestamps: UTC-naive (`TIMESTAMP WITHOUT TIME ZONE`)._

---

## Tables at a glance

| Table | Rows | Purpose |
|---|---|---|
| `cameras` | ~52 | Camera registry + calibration |
| `zones` | ~20 | Floor zones with capacity + access rules |
| `users` | ~50 | Auth users (guard / manager / admin) |
| `user_camera_permissions` | — | Which cameras each user can see |
| `persons` | ~500 | Enrolled employees / visitors |
| `person_embeddings` | ~3000 | 512-dim face embeddings (pgvector) |
| `tracking_events` | high-volume | One row per detection frame — partitioned by month |
| `ble_events` | medium | BLE badge reader events |
| `reid_matches` | medium | Cross-camera identity match log |
| `zone_presence` | medium | Zone entry/exit dwell-time records |
| `maintenance_windows` | ~100 | Scheduled alert-suppression windows |
| `alerts` | medium | Generated security alerts |
| `alert_routing` | ~20 | Rules: which alert → which channel |
| `alert_dispatches` | medium | Per-attempt delivery log |
| `anomaly_detectors` | 7 | Detector registry (enabled/disabled + config) |
| `person_clip_embeddings` | high-volume | CLIP embeddings for forensic search |
| `model_registry` | ~10 | ONNX model manifest (name, version, SHA) |
| `audit_log` | append-only | Immutable hash-chained audit trail |

---

## Topology

### `cameras`

| Column | Type | Notes |
|---|---|---|
| `camera_id` PK | integer | auto |
| `name` | varchar(200) | |
| `rtsp_url` | varchar(500) | contains credentials — never log |
| `is_active` | boolean | default true |
| `capability_tier` | varchar(10) | CHECK IN ('FULL','MID','LOW') |
| `profile_data` | text | JSON from camera profiler |
| `profiled_at` | timestamp | nullable |
| `shutter_type` | varchar(10) | CHECK IN ('rolling','global','unknown') |
| `model_overrides` | text | JSON per-camera model config |
| `worker_group` | integer | nullable — inference worker assignment |
| `homography_matrix` | text | JSON 9-float row-major 3×3; nullable until calibrated |
| `recalibrate_required_at` | timestamp | nullable — set by scheduler when drift detected |

### `zones`

| Column | Type | Notes |
|---|---|---|
| `zone_id` PK | integer | auto |
| `name` | varchar(200) | |
| `is_restricted` | boolean | default false |
| `max_capacity` | integer | nullable — triggers CROWD_DENSITY alert |
| `allowed_hours` | text | JSON time ranges; nullable |
| `loiter_threshold_s` | integer | default 180 — seconds before LOITERING alert |
| `polygon_json` | text | nullable — floor-plan polygon for homography projection |
| `adjacent_zone_ids` | text | JSON int array — pre-filter for cross-camera Re-ID |

---

## Users and permissions

### `users`

| Column | Type | Notes |
|---|---|---|
| `user_id` PK | integer | auto |
| `username` | varchar(100) | UNIQUE |
| `password_hash` | varchar(255) | bcrypt — never log |
| `role` | varchar(20) | CHECK IN ('guard','manager','admin') |
| `is_active` | boolean | default true |

### `user_camera_permissions`

| Column | Type | Notes |
|---|---|---|
| `perm_id` PK | integer | auto |
| `user_id` FK | integer | → users(user_id) ON DELETE CASCADE |
| `camera_id` FK | integer | → cameras(camera_id) ON DELETE CASCADE |

UNIQUE (`user_id`, `camera_id`)

---

## Persons and embeddings

### `persons`

| Column | Type | Notes |
|---|---|---|
| `person_id` PK | integer | auto |
| `employee_id` | varchar(50) | UNIQUE |
| `name` | varchar(200) | |
| `is_active` | boolean | default true |
| `badge_id` | varchar(64) | UNIQUE; nullable — BLE badge MAC |
| `thumbnail_path` | varchar(500) | nullable — storage backend relative key |
| `purged_at` | timestamp | nullable — set on GDPR purge |
| `created_at` | timestamp | UTC-naive default |

### `person_embeddings`

| Column | Type | Notes |
|---|---|---|
| `embedding_id` PK | bigint | auto |
| `person_id` FK | integer | → persons(person_id) ON DELETE CASCADE |
| `embedding` | vector(512) | pgvector — AdaFace IR101/WebFace12M L2-normalised |
| `quality_score` | float | CHECK 0.0–1.0 |
| `created_at` | timestamp | UTC-naive default |

Index: `ix_person_embeddings_person_id`

> FAISS is built from this table on startup. DB is authoritative; FAISS is cache.

---

## Tracking

### `tracking_events` _(partitioned RANGE on `event_ts`)_

| Column | Type | Notes |
|---|---|---|
| `event_id` PK part | bigint | composite PK with event_ts (partition requirement) |
| `event_ts` PK part | timestamp | partition key |
| `camera_id` FK | integer | → cameras(camera_id) ON DELETE NO ACTION |
| `local_track_id` | varchar(50) | ByteTrack local ID per camera |
| `global_track_id` | uuid | cross-camera identity UUID |
| `person_id` FK | integer | → persons(person_id) ON DELETE SET NULL; NULL after GDPR purge |
| `zone_id` | integer | not FK — zones can be retired |
| `ingest_ts` | timestamp | message arrival time |
| `bbox_x1/y1/x2/y2` | integer | CHECK x2>x1, y2>y1 |
| `floor_x`, `floor_y` | float | nullable — homography projection; NULL if camera not calibrated |
| `seq_id` | bigint | monotonic ingestion sequence |
| `resolved_via` | varchar(16) | CHECK IN ('face','body','ble','unknown'); nullable |

UNIQUE (`camera_id`, `local_track_id`, `event_ts`) — idempotency key for retry
Indexes: `global_track_id`, `person_id`, `camera_id`, `event_ts`

### `ble_events`

| Column | Type | Notes |
|---|---|---|
| `event_id` PK | bigint | auto |
| `person_id` FK | integer | → persons ON DELETE SET NULL; nullable |
| `badge_id` | varchar(64) | BLE MAC address |
| `zone_id` FK | integer | → zones ON DELETE SET NULL; nullable |
| `rssi` | integer | nullable — signal strength |
| `reader_id` | varchar(64) | fixed reader identifier |
| `event_ts` | timestamp | |

### `reid_matches`

| Column | Type | Notes |
|---|---|---|
| `reid_match_id` PK | bigint | auto |
| `global_track_id_1` | uuid | source track |
| `global_track_id_2` | uuid | matched track |
| `person_id` FK | integer | → persons ON DELETE SET NULL; nullable |
| `similarity` | float | cosine similarity at match time |
| `event_ts` | timestamp | |

### `zone_presence`

| Column | Type | Notes |
|---|---|---|
| `presence_id` PK | bigint | auto |
| `zone_id` FK | integer | → zones ON DELETE NO ACTION |
| `global_track_id` | uuid | |
| `entered_at` | timestamp | |
| `exited_at` | timestamp | nullable — NULL while still in zone; CHECK >= entered_at |

UNIQUE (`zone_id`, `global_track_id`, `entered_at`)

---

## Maintenance windows

### `maintenance_windows`

| Column | Type | Notes |
|---|---|---|
| `window_id` PK | integer | auto |
| `name` | varchar(200) | |
| `scope_type` | varchar(20) | CHECK IN ('CAMERA','ZONE') |
| `scope_id` | integer | camera_id or zone_id — not FK (flexible) |
| `schedule_type` | varchar(20) | CHECK IN ('ONE_TIME','RECURRING') |
| `starts_at` | timestamp | nullable — required for ONE_TIME |
| `ends_at` | timestamp | nullable — required for ONE_TIME; CHECK > starts_at |
| `cron_expr` | varchar(100) | nullable — required for RECURRING |
| `duration_minutes` | integer | nullable — required for RECURRING; CHECK > 0 |
| `suppress_alert_types` | text | JSON array of alert_type strings; NULL = suppress all |
| `is_active` | boolean | default true |
| `reason` | varchar(500) | nullable |
| `created_by` FK | integer | → users ON DELETE NO ACTION |
| `created_at` | timestamp | |

Index: `(scope_type, scope_id)`

---

## Alerts

### `alerts`

| Column | Type | Notes |
|---|---|---|
| `alert_id` PK | integer | auto |
| `alert_type` | varchar(30) | CHECK IN ('UNKNOWN_PERSON','PERSON_LOST','CROWD_DENSITY','INTRUSION','VIOLENCE','LOITERING','PPE_VIOLATION','SYSTEM_CRITICAL') |
| `severity` | varchar(10) | 'CRITICAL','HIGH','MEDIUM','LOW' |
| `state` | varchar(20) | CHECK IN ('active','acknowledged','resolved','suppressed') |
| `camera_id` FK | integer | → cameras ON DELETE NO ACTION; NULL only for SYSTEM_CRITICAL |
| `zone_id` | integer | not FK |
| `global_track_id` | uuid | nullable |
| `person_id` | integer | not FK — persons can be purged |
| `triggered_at` | timestamp | |
| `acknowledged_at` | timestamp | nullable; CHECK >= triggered_at |
| `acknowledged_by` FK | integer | → users ON DELETE SET NULL; nullable |
| `resolved_at` | timestamp | nullable; CHECK >= triggered_at and >= acknowledged_at |
| `suppressed_by_window_id` FK | integer | → maintenance_windows ON DELETE SET NULL; nullable |
| `dedup_key` | varchar(100) | nullable — FSM dedup within cooldown window |

Indexes: `alert_type`, `triggered_at`, `state`, partial index on `dedup_key` WHERE `state='active'`

### `alert_routing`

| Column | Type | Notes |
|---|---|---|
| `routing_id` PK | integer | auto |
| `alert_type` | varchar(30) | nullable — NULL = match all types |
| `severity` | varchar(10) | nullable — NULL = match all severities |
| `zone_id` | integer | nullable — NULL = match all zones |
| `channel` | varchar(20) | CHECK IN ('EMAIL','SLACK','TELEGRAM','WEBHOOK','WEBSOCKET') |
| `target` | varchar(500) | email address / Slack channel / webhook URL |
| `is_active` | boolean | default true |

### `alert_dispatches`

| Column | Type | Notes |
|---|---|---|
| `dispatch_id` PK | bigint | auto |
| `alert_id` FK | integer | → alerts ON DELETE CASCADE |
| `channel` | varchar(20) | |
| `target` | varchar(500) | |
| `attempt_n` | integer | default 1; up to 3 (exponential backoff 1s→4s→16s) |
| `dispatched_at` | timestamp | |
| `success` | boolean | |
| `error` | text | nullable |
| `response_code` | integer | nullable |

---

## Detectors and models

### `anomaly_detectors`

| Column | Type | Notes |
|---|---|---|
| `detector_id` PK | integer | auto |
| `alert_type` | varchar(30) | UNIQUE |
| `class_path` | varchar(200) | Python dotted path to detector class |
| `is_enabled` | boolean | default true |
| `config_json` | text | nullable — JSON override for detector thresholds |
| `model_version` | varchar(50) | nullable |
| `created_at` | timestamp | |
| `updated_at` | timestamp | |

Seeded rows: UNKNOWN_PERSON, PERSON_LOST, CROWD_DENSITY, INTRUSION, LOITERING, VIOLENCE, PPE_VIOLATION

### `model_registry`

| Column | Type | Notes |
|---|---|---|
| `model_id` PK | integer | auto |
| `model_name` | varchar(100) | |
| `model_version` | varchar(50) | |
| `file_path` | varchar(500) | relative path under `models/` |
| `sha256` | varchar(64) | verified on load |
| `purpose` | varchar(50) | e.g. 'face_detection', 'face_embedding', 'body_reid' |
| `fine_tunable` | boolean | default false |
| `metadata_json` | text | nullable |
| `created_at` | timestamp | |

---

## Forensic

### `person_clip_embeddings`

| Column | Type | Notes |
|---|---|---|
| `clip_emb_id` PK | bigint | auto |
| `global_track_id` | uuid | |
| `camera_id` FK | integer | → cameras ON DELETE NO ACTION |
| `event_ts` | timestamp | |
| `embedding` | vector(512) | CLIP 512-dim embedding for semantic search |
| `snapshot_path` | varchar(500) | storage backend relative key |

UNIQUE (`global_track_id`, `event_ts`)

---

## Audit

### `audit_log` _(append-only — never UPDATE/DELETE)_

| Column | Type | Notes |
|---|---|---|
| `audit_id` PK | bigint | auto |
| `event_type` | varchar(50) | e.g. 'PERSON_ENROLLED', 'PERSON_PURGED', 'ALERT_ACKED' |
| `actor_user_id` FK | integer | → users ON DELETE SET NULL; nullable (system events) |
| `target_type` | varchar(50) | nullable — 'person', 'camera', 'alert', etc. |
| `target_id` | varchar(50) | nullable — string ID of the affected entity |
| `payload` | text | nullable — JSON diff or extra context |
| `prev_hash` | varchar(64) | SHA-256 of previous row (hash chain) |
| `row_hash` | varchar(64) | SHA-256 of this row |
| `row_hash_version` | integer | server default 1 — bump if hash function changes |
| `event_ts` | timestamp | UTC-naive |

> Always write via `vms.db.audit.write_audit_event()` — never construct `AuditLog` directly.

---

## Relationships diagram

```
cameras ──< tracking_events >── persons ──< person_embeddings
   │              │
   │         zone_presence
   │
   └──< alerts >── alert_dispatches
         │
   maintenance_windows

zones ──< zone_presence
zones ──< ble_events

users ──< user_camera_permissions >── cameras
users ──< maintenance_windows (created_by)
users ──< audit_log (actor)
users ──< alerts (acknowledged_by)

persons ──< ble_events
persons ──< reid_matches
persons ──< zone_presence (via global_track_id — not FK)

cameras ──< person_clip_embeddings
cameras ──< reid_matches (via global_track_id — not FK)

alert_routing (standalone rules — no FK to alerts)
anomaly_detectors (standalone registry)
model_registry (standalone manifest)
```

---

## Constraints and invariants to know

| Rule | Where enforced |
|---|---|
| Partition key `event_ts` must appear in every UNIQUE constraint on `tracking_events` | Schema |
| `zone_id` in `tracking_events` and `alerts` is NOT a FK — zones can be retired | Intentional |
| `person_id` in `tracking_events` SET NULL on purge | ON DELETE SET NULL |
| Audit log rows are immutable — no UPDATE or DELETE | DB trigger Phase 5; code convention now |
| FAISS is rebuilt from `person_embeddings` — DB always wins | Architectural invariant |
| Thresholds (sim, conf) live in `vms/config.py` — never hard-code | Code convention |
