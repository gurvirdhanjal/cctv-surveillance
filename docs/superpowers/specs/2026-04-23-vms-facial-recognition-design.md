# Video Management System — Facial Recognition & Cross-Camera Tracking
**Design Specification** · 2026-04-23  
**Status:** Approved · Ready for implementation planning

---

## 1. Overview

A plant-floor video management system (VMS) supporting 52–53 cameras with identity-aware surveillance. The system detects, recognises, and tracks registered employees and unknown visitors across cameras in real time. It serves two primary user groups: **security guards** (live alerts, person tracking) and **plant management** (analytics, zone reports). Camera hardware specification is driven by this architecture document.

### Goals
- Detect unknown persons and raise real-time alerts
- Track registered employees across cameras using cross-camera re-identification
- Map person positions to a 2-D floor plan via homography
- Generate zone-level analytics and dwell-time reports
- Support investigation via timeline playback

### Non-goals (v1)
- Edge inference on smart cameras (architecture accommodates it later)
- Multi-site / multi-building deployments
- Public cloud hosting (on-premises GPU server only)

---

## 2. Existing Prototype

| Component | Status |
|---|---|
| Face detector | YOLOv8s-face + SCRFD 2.5g (ONNX, CPU) |
| Face embedder | AdaFace IR50 — 512-dim (ONNX, CPU) |
| Per-camera tracker | ByteTrack (config present, not wired) |
| Employee DB | Flat `.npy` file — 6 enrolled employees |
| Enrollment | CLI script — 6 webcam samples, averaged embedding |
| API / frontend | None |
| Database | None |
| Multi-camera | None |

The prototype is a solid inference baseline. The production system wraps it in a pipeline, database, API, and frontend.

---

## 3. Architecture — Modular Pipeline

**Pattern:** Separate OS processes for ingestion, inference, identity, and API. Redis Streams as the inter-process message bus. Single GPU server on-premises.

```
Cameras (52–53 × RTSP)
    │
    ▼  decoded frame → shared memory
Ingestion Workers (4 × Python process, ~13 cams each)
    │  Redis Stream: frames:groupA/B/C/D
    │  Payload: {cam_id, shm_name, seq_id, timestamp_ms}  ← no raw pixels in Redis
    ▼
Redis Streams  (MAXLEN 500 per group · consumer groups · persistent · replayable)
    │
    ▼  XREAD by consumer group
Inference Engine (GPU process pool)
    │  SCRFD 2.5g → face detect
    │  AdaFace IR50 → 512-dim embed
    │  YOLOv8n → person detect
    │  ByteTrack (per-camera instance) → confirmed tracklets
    │  Redis Stream: detections
    ▼
Identity & Tracking Service (Python process)
    │  FAISS flat IP index (5-min window · zone-adjacency pre-filter)
    │  Cross-camera Re-ID → global_track_id (UUID)
    │  Homography engine → floor_x, floor_y
    │  Alert FSM → alerts
    │  Redis Streams: tracking · alerts
    ▼
DB Writer (async batch)          FastAPI (REST + WebSocket)
    │  MSSQL Server                    │  Socket.io → browser
    │  batched flush 500ms/100 rows    │  throttled 5fps · diff-only positions
    ▼                                  ▼
                          React Frontend
                     Guard · Management · Admin
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| Shared memory for frames | Avoids sending raw pixels through Redis — only 24-byte metadata pointer |
| Redis Streams over Pub/Sub | Persistence, consumer groups, replay, XAUTOCLAIM recovery |
| Process isolation for GPU | Python GIL never blocks API server; OOM in inference doesn't kill API |
| Per-camera ByteTrack before Re-ID | Match confirmed tracklets, not noisy single detections |
| FAISS + zone adjacency pre-filter | Re-ID O(n) per query, not O(n²) naive cosine over all active tracks |
| Stateless API workers | Multiple FastAPI replicas behind load balancer; publish to Redis pub/sub for WebSocket fanout |

### Multi-Node Upgrade Path
Move Redis to a dedicated host → ingestion and inference workers become independently scalable across machines. Worker heartbeat registry enables auto-failover detection. Kafka replaces Redis Streams when throughput demands it — same consumer-group API shape, no logic rewrite.

---

## 4. Shared Memory Safety

SHM slot layout (per camera): first 16 bytes = header `{sequence_id: u64, timestamp_ms: u64}`, followed by raw BGR frame bytes.

**Before every GPU read:**
1. Read header → validate `now_ms - timestamp_ms < STALE_THRESHOLD_MS (200ms)` AND `seq_id > last_seen_seq`
2. On stale: XACK, skip frame, increment `frames_dropped` metric
3. On worker crash: supervisor reads `shm_registry:{worker_pid}` Redis hash → `shm_unlink` all owned segments before restart

---

## 5. Backpressure & Frame Dropping

- Each camera has a single-slot Redis Hash entry `latest_frame:{cam_id}` — ingestion worker overwrites on every frame
- Inference worker reads latest slot; stale frames (age > `STALE_THRESHOLD_MS`) are skipped
- Redis Streams capped at `MAXLEN 500` per group (rolling window) — oldest entries auto-trimmed
- Consumer lag monitored: if `XLEN - consumer_offset > 500`: admin alert emitted

---

## 6. Inference Pipeline

### Models
| Model | Purpose | Input | Output |
|---|---|---|---|
| SCRFD 2.5g | Face detection | 640×640 BGR | Bboxes + landmarks (5pt) |
| AdaFace IR50 | Face embedding | 112×112 face crop | 512-dim float32 |
| YOLOv8n | Person detection | 640×640 BGR | Person bboxes |
| ByteTrack | Per-camera tracking | Person bboxes per frame | Stable local_track_id |

### Inference Runtime
- All models loaded as ONNX with `CUDAExecutionProvider` on GPU process startup
- TensorRT compilation optional for YOLOv8n (2–3× throughput gain)
- GPU batch: group frames from multiple cameras into single SCRFD/YOLOv8 batch call
- Run-every-N config per camera (default N=1; lower-priority zones can use N=3)

### Recognition Thresholds
| Threshold | Value | Purpose |
|---|---|---|
| `SCRFD_CONF` | 0.60 | Face detection minimum confidence |
| `ADAFACE_MIN_SIM` | 0.72 | DB match — known person |
| `REID_CROSS_CAM_SIM` | 0.65 | Cross-camera tracklet match |
| `REID_MARGIN` | 0.08 | Best minus second-best similarity |
| `MIN_BLUR` | 25.0 | Laplacian variance — skip blurry crops |
| `MIN_FACE_PX` | 40 | Minimum face bbox dimension |

---

## 7. Cross-Camera Re-Identification

1. **Zone adjacency pre-filter:** only compare incoming tracklet against active tracklets in the same zone or adjacent zones (`zones.adjacent_zone_ids`). Eliminates irrelevant comparisons.
2. **Time window:** only tracklets seen within the last 5 minutes are in the FAISS index
3. **Match decision:** cosine similarity ≥ 0.65 AND margin ≥ 0.08 → assign existing `global_track_id`; else create new UUID
4. **DB identity resolution:** match against `person_embeddings` table; sim ≥ 0.72 → assign `person_id`
5. **All matches logged** to `reid_matches` with confidence and `match_source`

### Correction Propagation
When a guard manually corrects an identity:
1. Write to `reid_matches` with `match_source='manual'`
2. Identity service reads `corrections` Redis Stream → UPDATE `tracking_events.person_id` WHERE `global_track_id = X`
3. FastAPI emits `track_corrected` WebSocket event → React store patches all matching entries

---

## 8. Homography

Each camera has a precomputed 3×3 homography matrix `H` stored in `cameras.homography_matrix` (JSON, row-major 9 floats). Applied at startup — never recomputed at runtime.

**Calibration (4-step wizard in admin UI):**
1. Select camera
2. Capture calibration frame
3. Mark 4 reference points on camera frame — match same points on floor plan image
4. Compute `H` via `cv2.findHomography` — wizard validates reprojection error < 2px before saving

`floor_x, floor_y` stored as `NULL` in `tracking_events` if camera has no calibrated `H` matrix.

---

## 9. Alert Finite State Machine

Each alert type is an independent FSM keyed by `(global_track_id, alert_type)`. FSM evaluates on `event.event_ts` (not arrival order) — events arriving > 5s late are discarded.

| Alert | Entry Condition | Sustained Duration | Cooldown | Reset |
|---|---|---|---|---|
| `UNKNOWN_PERSON` | `person_id IS NULL` | > 500ms in frame | 60s per zone | Identity confirmed |
| `PERSON_LOST` | Absent from all cameras | > 30s | 120s | Re-detected anywhere |
| `CROWD_DENSITY` | Persons in zone > `max_capacity` | > 10s continuous | 300s per zone | Count drops below threshold |

**Dedup key:** `(alert_type + zone_id)` within 60s window — one alert per window regardless of event frequency.

**Alert storm protection:** max 10 active alerts per zone stored; frontend groups same `global_track_id` alerts ("+ 12 similar").

---

## 10. Database Schema (MSSQL Server)

### Tables

**persons** — registered employees and unknown visitor records  
`person_id INT IDENTITY PK · employee_id NVARCHAR(50) · full_name NVARCHAR(200) · department NVARCHAR(100) · person_type NVARCHAR(20) · thumbnail_path NVARCHAR(500) · is_active BIT DEFAULT 1 · created_at DATETIME2`

**person_embeddings** — multiple face embeddings per person  
`embedding_id INT IDENTITY PK · person_id INT FK · embedding VARBINARY(2048) · quality_score FLOAT · source NVARCHAR(20) · created_at DATETIME2`  
*FAISS index rebuilt from this table at service startup. MSSQL is source of truth.*

**cameras** — camera registry and precomputed homography  
`camera_id INT IDENTITY PK · name NVARCHAR(100) · rtsp_url NVARCHAR(500) · worker_group NCHAR(1) · homography_matrix NVARCHAR(MAX) · fov_polygon NVARCHAR(MAX) · resolution_w INT · resolution_h INT · is_active BIT`

**zones** — named plant areas  
`zone_id INT IDENTITY PK · name NVARCHAR(100) · polygon NVARCHAR(MAX) · max_capacity INT · is_restricted BIT · adjacent_zone_ids NVARCHAR(MAX) · color_hex NCHAR(7)`

**tracking_events** — high-write event log (partitioned by month on `event_ts`)  
`event_id BIGINT IDENTITY PK · global_track_id UNIQUEIDENTIFIER · person_id INT · camera_id INT NOT NULL · zone_id INT · local_track_id INT NOT NULL · bbox_x1 INT · bbox_y1 INT · bbox_x2 INT · bbox_y2 INT · floor_x FLOAT · floor_y FLOAT · confidence FLOAT · event_ts DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()`  
*`local_track_id`: ByteTrack-assigned ID per camera, used in the idempotency constraint.*

**alerts** — alert log with explicit FSM state  
`alert_id INT IDENTITY PK · state NVARCHAR(20) · alert_type NVARCHAR(30) · severity NVARCHAR(10) · person_id INT · global_track_id UNIQUEIDENTIFIER · camera_id INT · zone_id INT · triggered_at DATETIME2 · acknowledged_at DATETIME2 · resolved_at DATETIME2 · acknowledged_by INT FK users · snapshot_path NVARCHAR(500)`

**reid_matches** — cross-camera identity match audit trail  
`match_id BIGINT IDENTITY PK · global_track_id UNIQUEIDENTIFIER · person_id INT NOT NULL · confidence FLOAT · match_source NVARCHAR(20) · from_camera_id INT · to_camera_id INT · matched_at DATETIME2`

**zone_presence** — dwell time for analytics and heatmaps  
`presence_id BIGINT IDENTITY PK · zone_id INT NOT NULL · global_track_id UNIQUEIDENTIFIER · person_id INT · entered_at DATETIME2 NOT NULL · exited_at DATETIME2 · dwell_seconds AS (DATEDIFF(SECOND, entered_at, ISNULL(exited_at, SYSUTCDATETIME())))`

**users** — system users  
`user_id INT IDENTITY PK · username NVARCHAR(100) UNIQUE · email NVARCHAR(200) UNIQUE · password_hash NVARCHAR(200) · role NVARCHAR(20) · is_active BIT DEFAULT 1 · created_at DATETIME2 · last_login DATETIME2`

**user_zone_permissions** — zone-level access control  
`user_id INT FK · zone_id INT FK · PRIMARY KEY (user_id, zone_id)`

**user_camera_permissions** — camera-level access control  
`user_id INT FK · camera_id INT FK · PRIMARY KEY (user_id, camera_id)`

### Index Strategy

```sql
-- tracking_events (14M+ rows/day)
CREATE INDEX idx_track_time     ON tracking_events (event_ts DESC)
CREATE INDEX idx_track_person   ON tracking_events (person_id, event_ts DESC)
CREATE INDEX idx_track_camera   ON tracking_events (camera_id, event_ts DESC)
CREATE INDEX idx_global_track   ON tracking_events (global_track_id)

-- zone_presence
CREATE INDEX idx_zone_time      ON zone_presence (zone_id, entered_at DESC)
CREATE INDEX idx_person_pres    ON zone_presence (person_id)
CREATE INDEX idx_zone_active    ON zone_presence (zone_id, entered_at DESC)
  WHERE exited_at IS NULL   -- "who's inside right now?"

-- alerts
CREATE INDEX idx_alert_active   ON alerts (state, triggered_at DESC)
  WHERE state = 'active'
CREATE INDEX idx_alert_type     ON alerts (alert_type, triggered_at DESC)
```

### MSSQL-specific Notes
- `tracking_events` partitioned by month using `PARTITION FUNCTION pf_monthly(DATETIME2)`. New partition added monthly via scheduled job.
- All JSON fields (`polygon`, `homography_matrix`, `adjacent_zone_ids`) validated against Pydantic schemas before write.
- DB writer uses SQLAlchemy `executemany` bulk insert, flushed every 500ms or 100 rows — never row-by-row.
- Idempotency: UNIQUE constraint on `(camera_id, local_track_id, event_ts)` in `tracking_events`; writer uses MSSQL `MERGE` (upsert) on retry — zero double-writes.

---

## 11. API Design (FastAPI)

### Authentication
JWT tokens, 8h expiry. Role-based route guards: `guard`, `manager`, `admin`. Zone/camera access enforced via `user_zone_permissions` / `user_camera_permissions` in FastAPI dependency.

### Key Endpoints

```
GET  /api/persons/search?q=              person lookup (name, employee_id)
GET  /api/persons/{id}/timeline?from=&to= ordered tracking events for one person
GET  /api/state/snapshot                 current active tracks + alerts + zone occupancy
GET  /api/cameras/{id}/snapshot          latest JPEG frame (2s cache)
GET  /api/zones/{id}/presence?from=&to=  dwell data for analytics
POST /api/persons                        enroll new person
POST /api/persons/{id}/embeddings        add embedding (enrollment or re-enroll)
PATCH /api/alerts/{id}/acknowledge
PATCH /api/alerts/{id}/assign
PATCH /api/alerts/{id}/resolve
POST /api/cameras/{id}/calibrate         save homography matrix
POST /api/zones                          create zone
```

### WebSocket Events (Socket.io)

```
person_location  {global_track_id, person_id, camera_id, bbox, floor_x, floor_y, ts}
                 → throttled 5fps, diff-only, keyed by global_track_id
alert_fired      {alert_id, alert_type, severity, camera_id, zone_id, ts}
                 → immediate, no throttle
track_corrected  {global_track_id, new_person_id, ts}
                 → immediate
camera_snapshot  {camera_id, url, ts}
                 → every 2s per subscribed camera
worker_health    {worker_id, status, cam_count, ts}
                 → on change
```

**WebSocket fanout:** FastAPI publishes events to Redis pub/sub channel `ws_events`. All FastAPI replicas subscribe and push to their own connected clients. Horizontal scale = add replicas.

**Reconnect rehydration:** on Socket.io `connect` event, client calls `GET /api/state/snapshot` before processing first diff event.

---

## 12. Frontend Design (React + TypeScript)

### Stack
- **Framework:** React 18 + TypeScript + Vite
- **Styling:** Tailwind CSS + shadcn/ui
- **Server state:** TanStack Query
- **Client state:** Zustand
- **Real-time:** Socket.io client
- **Maps/floor plan:** Leaflet.js (image overlay + polygon drawing + live person dots)
- **Charts:** Recharts
- **Video:** HLS.js (focused tile only)
- **Auth:** JWT, role-based route guards
- **Forms:** React Hook Form + Zod validation

### Three Views

**Guard / Live**
- Top bar: global search (Cmd+K) + system status strip (camera count, worker health, GPU)
- Camera grid: JPEG snapshots by default (2s refresh polling), click-to-stream HLS. Max 4 concurrent HLS at any time.
- Alert sidebar: sorted by severity → recency, grouped by `global_track_id`, assign/dismiss/notes per alert, auto-dismiss timer configurable
- Follow Person panel: auto-switches focused camera feed as person moves, shows movement timeline strip, consistent colour/label across all cameras

**Management / Analytics**
- Time scrubber: date/time slider with playback mode — reconstructs person movement trails from `tracking_events` for investigation
- Floor plan heatmap: Leaflet image overlay, zone opacity = dwell intensity, live person dots, trail dots in scrub window
- Stats: daily person count, average dwell, unknown count, camera uptime
- Person lookup: search → last seen + 24h journey + per-zone dwell times
- CSV export of zone presence data

**Admin**
- Person enrollment: wizard — name/ID → capture from camera or upload → 6-sample quality check → save to DB
- Camera config: RTSP URL, worker group, homography calibration wizard (4-step, validates reprojection error < 2px, undo last point)
- Zone editor: polygon draw on floor plan, 4-step wizard (draw → configure → assign cameras → set permissions), undo stack
- Permissions: toggle zone/camera access per user
- System health: per-worker status, GPU utilisation, MSSQL write queue depth, Redis stream lag

---

## 13. Error Handling & Recovery

| Failure | Severity | Recovery | Visibility |
|---|---|---|---|
| Camera RTSP disconnect | HIGH | Exponential backoff (1→2→4→8→60s). After 3 fails: mark `is_active=false`. Worker continues other cameras. | Status bar + admin alert |
| Ingestion worker crash | HIGH | Systemd restart < 5s. XAUTOCLAIM recovers unACKed messages after 10s. | Health panel warning within 15s |
| GPU inference OOM / crash | CRITICAL | Catch OOM → halve batch size → retry. On crash: supervisor restart. CPU fallback for 1 priority group. | Admin alert + health panel |
| Redis unavailable | CRITICAL | Workers buffer 200 frames/cam in-memory deque. Retry every 2s. Drain on recovery. Drop frames > 5s old. | Degraded mode banner (see §14) |
| MSSQL write failure | HIGH | 3 retries with backoff. On persistent fail: circular memory buffer 50k rows + JSON file log for manual replay. | Health panel + write error metric |
| Re-ID false match | MEDIUM | Guard corrects via UI → `corrections` stream → cascade DB update + `track_corrected` WS event. | Wrong name shown, correctable |
| Alert storm | MEDIUM | Server dedup 60s window per `(type+zone)`. Max 10 active per zone. Client groups same-track alerts. | "+ N similar" grouping |
| Shared memory stale/corrupt | MEDIUM | Header validation (seq_id + timestamp) before every read. Stale: skip + XACK. Crash cleanup via `shm_registry` in Redis. | Logged; invisible to guard |
| WebSocket disconnect | LOW | Socket.io auto-reconnect. On reconnect: `GET /api/state/snapshot` → full rehydration. | Reconnecting indicator |
| Homography miscalibration | MEDIUM | Wizard blocks save if reprojection error ≥ 2px. `floor_x/y` stored as NULL for uncalibrated cameras. | Admin notified; floor dots absent |
| Poison message (Redis) | LOW | XAUTOCLAIM: after 3 deliveries without ACK → move to `dead_letter` stream + XACK original. | Logged for inspection |

---

## 14. Degraded Mode (Redis Outage)

Explicitly documented behaviour when Redis is unavailable:

| Component | Behaviour |
|---|---|
| Ingestion workers | Continue decoding, buffer 200 frames/cam in-memory deque |
| Inference | Runs locally; **Re-ID disabled** — each detection gets ephemeral UUID, no cross-camera identity |
| Alerts | **Not delivered** to frontend |
| DB writes | Buffered to local JSON file (max 100MB, oldest dropped) for replay on recovery |
| Frontend | Shows "System degraded — Re-ID offline" banner; camera snapshots still refresh via direct API calls |

---

## 15. Event Versioning

All Redis Stream events carry:
- `seq_id`: monotonic u64 per source worker (reset on restart)
- `schema_version: "1"`: consumers log mismatches, enabling future contract evolution
- `timestamp_ms`: epoch milliseconds at frame capture (not at processing time)

FSM and Re-ID evaluate on `timestamp_ms`, not arrival order.

---

## 16. Observability

- Each worker emits structured JSON logs to stdout → captured by systemd journal or file sink
- Prometheus metrics endpoint per process: inference latency (p50/p95/p99), frames dropped, Redis stream lag, DB write queue depth, GPU utilisation
- Grafana dashboard: per-camera detection rate, alert frequency, worker health
- Worker heartbeat: Redis key `heartbeat:{worker_id}` with 15s TTL, refreshed every 10s. Health monitor checks every 10s and emits admin alert on expiry.

---

## 17. Camera Hardware Guidance

Architecture-derived minimum spec for production cameras:

| Requirement | Minimum | Recommended |
|---|---|---|
| Protocol | RTSP H.264 | RTSP H.264/H.265 |
| Resolution | 1080p (1920×1080) | 2MP–4MP |
| Frame rate | 15fps | 25–30fps |
| Shutter type | Rolling or global | Global shutter preferred for moving subjects |
| Low-light | IR night vision | True WDR + IR |
| FOV | 90°–110° | Adjustable varifocal |
| Network | PoE (802.3af) | PoE+ (802.3at) |
| Smart features | Optional | ONVIF compliance preferred |

Rolling shutter is acceptable with ByteTrack (motion blur handled at tracking level). Global shutter preferred at entry/exit points where people move quickly.

---

## 18. Development Phases

### Phase 1 — Foundation (webcam first)
- MSSQL schema + migrations (Alembic)
- Ingestion worker (webcam → shared memory → Redis Streams)
- Inference engine (SCRFD + AdaFace + ByteTrack) wired to pipeline
- Basic FastAPI: enrollment, recognition, health endpoints
- Per-camera ByteTrack producing confirmed tracklets

### Phase 2 — Identity & Tracking
- Cross-camera Re-ID service (FAISS + zone adjacency)
- Homography engine + calibration wizard
- Alert FSM (unknown, lost, crowd)
- `reid_matches` audit trail + correction propagation

### Phase 3 — Frontend
- React scaffold: Guard view (snapshots + HLS + Follow Person)
- Management view (floor plan + time scrubber + analytics)
- Admin view (enrollment wizard + zone editor + health panel)
- WebSocket integration (Socket.io diff updates + reconnect rehydration)

### Phase 4 — Production Hardening
- Shared memory cleanup + safety headers
- Redis Streams consumer lag monitoring + dead-letter
- DB idempotency (MERGE + unique constraints)
- Prometheus metrics + Grafana dashboard
- Load testing at 52-camera scale
- Systemd unit files for all workers

### Phase 5 — Camera Rollout
- Procure cameras per §17 spec
- RTSP integration + per-camera homography calibration
- Zone polygon mapping on real floor plan CAD
- Security review (auth, RTSP credential encryption, role permissions)

---

## 19. Technology Stack Summary

| Layer | Technology |
|---|---|
| Face detection | SCRFD 2.5g (ONNX + CUDAExecutionProvider) |
| Face embedding | AdaFace IR50 (ONNX + CUDA) |
| Person detection | YOLOv8n (ONNX / TensorRT optional) |
| Per-camera tracking | ByteTrack |
| Cross-camera Re-ID | FAISS flat IP index |
| Message bus | Redis Streams (→ Kafka upgrade path) |
| IPC frames | Python multiprocessing.shared_memory |
| Database | MSSQL Server (SQLAlchemy + pyodbc) |
| Backend API | FastAPI + Uvicorn |
| WebSocket | Socket.io (server + client) |
| Frontend framework | React 18 + TypeScript + Vite |
| Frontend styling | Tailwind CSS + shadcn/ui |
| Frontend maps | Leaflet.js |
| Frontend charts | Recharts |
| Frontend video | HLS.js |
| DB migrations | Alembic |
| Process supervision | Systemd (Linux) or NSSM (Windows) |
| Metrics | Prometheus + Grafana |
