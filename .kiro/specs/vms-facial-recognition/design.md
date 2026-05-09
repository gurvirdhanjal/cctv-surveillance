# Design Document

## Overview

The VMS is a modular, multi-process pipeline running on a single on-premises GPU server. Separate OS processes handle ingestion, GPU inference, identity resolution, database writes, and the REST/WebSocket API. Redis Streams serve as the inter-process message bus. Raw frame pixels never travel through Redis — only 24-byte metadata pointers referencing shared memory segments.

---

## Architecture

```
Cameras (52–53 × RTSP / webcam)
    │
    ▼  decoded frame → shared memory (SHM_Slot)
Ingestion Workers (4 × Python process, ~13 cams each)
    │  Redis Stream: frames:groupA/B/C/D  (MAXLEN 500)
    │  Payload: {cam_id, shm_name, seq_id, timestamp_ms}
    ▼
Redis Streams  (consumer groups · persistent · replayable)
    │
    ▼  XREADGROUP by consumer group
Inference Engine (GPU process)
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
    │  PostgreSQL + pgvector           │  Socket.io → browser
    │  flush 500ms / 100 rows          │  throttled 5fps · diff-only
    ▼                                  ▼
                          React Frontend
                     Guard · Management · Admin
```

---

## Component Design

### Shared Memory (SHM_Slot)

Each camera owns one shared memory segment. Layout:

```
Bytes 0–7:   seq_id      (uint64, big-endian)
Bytes 8–15:  timestamp_ms (uint64, big-endian)
Bytes 16+:   raw BGR frame (width × height × 3)
```

Before every GPU read the Inference_Engine validates:
- `now_ms - timestamp_ms < 200` (stale threshold)
- `seq_id > last_seen_seq` (no reprocessing)

On worker crash, the supervisor reads `shm_registry:{worker_pid}` from Redis and calls `shm_unlink` on all owned segments before restart.

### Redis Streams

- Four ingestion streams: `frames:groupA`, `frames:groupB`, `frames:groupC`, `frames:groupD`
- One detections stream: `detections`
- One corrections stream: `corrections`
- One dead-letter stream: `dead_letter`
- All streams capped at MAXLEN 500 with approximate trimming
- Consumer groups used for all streams; XAUTOCLAIM recovers unACKed messages after 10s
- All events carry `schema_version: "1"`, `seq_id`, and `timestamp_ms`

### Inference Engine

Models loaded at startup as ONNX with `CUDAExecutionProvider`:

| Model | Input | Output |
|---|---|---|
| SCRFD 2.5g | 640×640 BGR | Face bboxes + confidence |
| AdaFace IR50 | 112×112 face crop | 512-dim float32 embedding |
| YOLOv8n | 640×640 BGR | Person bboxes |
| ByteTrack | Person bboxes per frame | Stable local_track_id |

Frames from multiple cameras are batched into a single SCRFD/YOLOv8 call. Per-camera ByteTrack instances run after person detection. Face crops are extracted, blur-checked (Laplacian variance ≥ 25.0), and embedded. Confirmed tracklets are published to the `detections` stream.

Recognition thresholds:

| Threshold | Value |
|---|---|
| SCRFD_CONF | 0.60 |
| ADAFACE_MIN_SIM | 0.72 |
| REID_CROSS_CAM_SIM | 0.65 |
| REID_MARGIN | 0.08 |
| MIN_BLUR | 25.0 |
| MIN_FACE_PX | 40 |
| STALE_THRESHOLD_MS | 200 |

### Identity & Tracking Service

1. Reads from `detections` stream
2. Zone adjacency pre-filter: compare only against tracklets in same or adjacent zones
3. FAISS flat IP cosine search over 5-minute active window
4. Match decision: sim ≥ 0.65 AND margin ≥ 0.08 → reuse `global_track_id`; else new UUID
5. DB identity resolution: sim ≥ 0.72 → assign `person_id`
6. Homography projection → `floor_x`, `floor_y`
7. Alert FSM evaluation
8. Publishes to `tracking` and `alerts` streams

### Alert FSM

Each FSM instance is keyed by `(global_track_id, alert_type)`. Evaluates on `timestamp_ms` (event time). Events > 5s late are discarded.

| Alert | Entry | Sustained | Cooldown | Reset |
|---|---|---|---|---|
| UNKNOWN_PERSON | person_id IS NULL | > 500ms | 60s per zone | Identity confirmed |
| PERSON_LOST | Absent all cameras | > 30s | 120s | Re-detected anywhere |
| CROWD_DENSITY | Count > max_capacity | > 10s | 300s per zone | Count drops below threshold |

Dedup key: `(alert_type, zone_id)` within 60s window. Max 10 active alerts per zone.

### DB Writer

- Reads from `tracking` stream
- Batches rows using SQLAlchemy `executemany`
- Flushes every 500ms or 100 rows
- Uses `INSERT ... ON CONFLICT DO NOTHING` on `(camera_id, local_track_id, event_ts)` for idempotency
- On failure: 3 retries with backoff → circular in-memory buffer (50k rows) → JSON file overflow

### Event Versioning

All Redis Stream events carry three mandatory fields:
- `schema_version: "1"` — consumers log mismatches; enables future contract evolution
- `seq_id` — monotonic u64 per source worker (resets on restart)
- `timestamp_ms` — epoch milliseconds at frame capture, not at processing time

FSM and Re-ID evaluate on `timestamp_ms`, not arrival order. Events > 5s late are discarded.

### FastAPI API Server

- Stateless; multiple replicas supported
- JWT auth, 8h expiry, roles: `guard`, `manager`, `admin`
- Zone/camera access enforced via dependency injection
- WebSocket fanout via Redis pub/sub channel `ws_events`
- On reconnect: client calls `GET /api/state/snapshot` before processing diffs

---

## Database Schema (PostgreSQL + pgvector)

17 tables:

- **cameras**: camera registry, RTSP URLs, homography matrices, FOV polygons, capability tier
- **zones**: named plant areas with polygons, capacity, adjacency, and access flags
- **users**: system users with bcrypt password hashes
- **user_camera_permissions**: camera-level access control (composite PK)
- **persons**: registered employees and unknown visitor records
- **person_embeddings**: multiple 512-dim `Vector(512)` embeddings per person (FAISS source of truth)
- **maintenance_windows**: scheduled alert-suppression windows (one-time or recurring)
- **alerts**: alert log with FSM state (active / suppressed / acknowledged / resolved)
- **alert_routing**: rules mapping alert type + zone to notification channels
- **alert_dispatches**: per-attempt delivery log for each alert channel
- **tracking_events**: high-write event log, partitioned by month on `event_ts` (Phase 5)
- **reid_matches**: cross-camera identity match audit trail
- **zone_presence**: dwell-time records with `entered_at` / `exited_at`
- **anomaly_detectors**: per-type detector configuration rows
- **person_clip_embeddings**: 512-dim CLIP embeddings for forensic text search
- **model_registry**: ML model version catalogue with SHA-256 checksums
- **audit_log**: immutable hash-chain event log

Key indexes on `tracking_events`: `event_ts DESC`, `(person_id, event_ts DESC)`, `(camera_id, event_ts DESC)`, `global_track_id`. Partial index on `alerts` for `state = 'active'`.

---

## API Endpoints

```
GET  /api/health
GET  /api/state/snapshot
GET  /api/persons/search?q=
GET  /api/persons/{id}/timeline?from=&to=
POST /api/persons
POST /api/persons/{id}/embeddings
GET  /api/cameras/{id}/snapshot
POST /api/cameras/{id}/calibrate
GET  /api/zones/{id}/presence?from=&to=
POST /api/zones
PATCH /api/alerts/{id}/acknowledge
PATCH /api/alerts/{id}/assign
PATCH /api/alerts/{id}/resolve
```

WebSocket events (Socket.io): `person_location`, `alert_fired`, `track_corrected`, `camera_snapshot`, `worker_health`.

---

## Frontend (React + TypeScript)

Stack: React 18 + TypeScript + Vite · Tailwind CSS + shadcn/ui · TanStack Query · Zustand · Socket.io client · Leaflet.js · Recharts · HLS.js · React Hook Form + Zod.

Three views:
- **Guard / Live**: camera grid (JPEG snapshots, click-to-HLS, max 4 concurrent), alert sidebar, Follow Person panel
- **Management / Analytics**: floor plan heatmap, time scrubber, person lookup, CSV export
- **Admin**: enrollment wizard, camera config + homography calibration, zone editor, permissions, health panel

---

## Technology Stack

| Layer | Technology |
|---|---|
| Face detection | SCRFD 2.5g (ONNX + CUDAExecutionProvider) |
| Face embedding | AdaFace IR50 (ONNX + CUDA) |
| Person detection | YOLOv8n (ONNX / TensorRT optional) |
| Per-camera tracking | ByteTrack (ultralytics) |
| Cross-camera Re-ID | FAISS flat IP index |
| Message bus | Redis Streams |
| IPC frames | Python multiprocessing.shared_memory |
| Database | PostgreSQL 16 + pgvector (SQLAlchemy 2.x + psycopg2-binary) |
| Migrations | Alembic |
| Backend API | FastAPI + Uvicorn |
| WebSocket | Socket.io |
| Frontend | React 18 + TypeScript + Vite |
| Styling | Tailwind CSS + shadcn/ui |
| Maps | Leaflet.js |
| Charts | Recharts |
| Video | HLS.js |
| Config | pydantic-settings 2.x |
| Auth | python-jose (JWT) + bcrypt |
| Process supervision | Systemd (Linux) |
| Metrics | Prometheus + Grafana |

---

## Error Handling

| Failure | Recovery |
|---|---|
| Camera RTSP disconnect | Exponential backoff 1→2→4→8→60s; after 3 fails mark `is_active=false` |
| Ingestion worker crash | Systemd restart < 5s; XAUTOCLAIM recovers after 10s |
| GPU OOM | Catch OOM → halve batch size → retry; on crash: supervisor restart |
| Redis unavailable | In-memory buffer 200 frames/cam; retry every 2s; drain on recovery |
| PostgreSQL write failure | 3 retries; circular buffer 50k rows; JSON file overflow |
| Re-ID false match | Guard corrects via UI → corrections stream → cascade DB update |
| Poison message | After 3 unACKed deliveries → dead_letter stream |
| WebSocket disconnect | Socket.io auto-reconnect + snapshot rehydration |
| Homography miscalibration | Wizard blocks save if reprojection error ≥ 2px |

---

## Development Phases

- **Phase 1 — Foundation**: PostgreSQL schema, ingestion worker, inference engine (SCRFD + AdaFace + ByteTrack), basic FastAPI (enrollment + health). ← current scope
- **Phase 2 — Identity & Tracking**: Cross-camera Re-ID, homography engine, Alert FSM, reid_matches audit trail
- **Phase 3 — Frontend**: React scaffold, Guard/Management/Admin views, WebSocket integration
- **Phase 4 — Production Hardening**: SHM safety, Redis lag monitoring, DB idempotency, Prometheus/Grafana, load testing
- **Phase 5 — Camera Rollout**: RTSP integration, homography calibration, zone mapping, security review
