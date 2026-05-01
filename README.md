# VMS — Plant-Floor Video Management System

Production-grade video management system for industrial sites. Combines facial recognition, cross-camera tracking, head counting, and multi-model anomaly detection (intrusion, violence, loitering) into a single on-premises deployment that runs on **existing IP cameras** — smart cameras are an optional upgrade.

[![Phase](https://img.shields.io/badge/phase-1A%20foundation-blue)]() [![Stack](https://img.shields.io/badge/stack-Python%203.11%20%C2%B7%20FastAPI%20%C2%B7%20React%2018%20%C2%B7%20MSSQL-1f4e79)]() [![Status](https://img.shields.io/badge/status-design%20hardened-green)]()

```
┌────────────────────────────────────────────────────────────────────────────┐
│  v1: 52 cameras  ·  v2: 200+ via two-node  ·  v2.x: multi-site / Kafka     │
│  GPU floor: 1 × A4000-class  ·  Anomalies: intrusion · violence · loiter   │
│  Alert latency: <250ms  ·  Frame staleness drop: 200ms  ·  SLA tiers per cam│
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Table of contents

- [What this is](#what-this-is)
- [System architecture](#system-architecture)
- [Frame-to-alert data flow](#frame-to-alert-data-flow)
- [Anomaly detector pipeline](#anomaly-detector-pipeline)
- [Alert lifecycle](#alert-lifecycle)
- [Multi-channel alert delivery](#multi-channel-alert-delivery)
- [Camera capability tiering](#camera-capability-tiering)
- [Database schema (key tables)](#database-schema-key-tables)
- [Deployment topology](#deployment-topology)
- [Phase progression](#phase-progression)
- [Frontend architecture](#frontend-architecture)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Repository layout](#repository-layout)
- [Documentation map](#documentation-map)
- [Testing](#testing)
- [Operations](#operations)
- [Contributing](#contributing)

---

## What this is

The system serves three audiences in one deployment:

| Audience | Primary task | Daily touchpoints |
|---|---|---|
| **Security guards** | Watch live feeds, respond to alerts | Live camera tiles, alert sidebar, follow-person, head count |
| **Plant managers** | Investigate incidents, analyse operations | Timeline scrubber, floor heatmap, dwell reports, forensic search |
| **System administrators** | Configure cameras, zones, users, models, schedules | Enrolment wizard, homography calibrator, maintenance calendar, model manager, audit verification |

The **v1 deployment target** is a single-site 52-camera plant; the architecture scales to 200+ cameras via two-node deployment and >200 via Kafka migration with no logic rewrite.

---

## System architecture

The pipeline is a chain of OS-isolated processes connected by a Redis Streams message bus, with shared memory for raw frame transport so doubling the camera count does not double the bus bandwidth.

```mermaid
flowchart LR
    subgraph Cameras["Cameras (RTSP)"]
        C1[Cam 1..13]
        C2[Cam 14..26]
        C3[Cam 27..39]
        C4[Cam 40..52]
    end

    subgraph Ingestion["Ingestion Workers (CPU)"]
        IW1[Worker A]
        IW2[Worker B]
        IW3[Worker C]
        IW4[Worker D]
    end

    SHM[("Shared Memory<br/>(raw frames)")]

    subgraph Bus["Redis Streams"]
        FS["frames:groupA..D<br/>MAXLEN 500"]
        DS[detections]
        TS[tracking]
        AS[alerts]
        CS[corrections]
    end

    subgraph Inference["GPU Inference Engine"]
        SCRFD[SCRFD 2.5g<br/>face detect]
        YOLO[YOLOv8n<br/>person detect]
        ADAFACE[AdaFace IR50<br/>face embed]
        BYTE[ByteTrack<br/>per-camera]
        VIOLENCE[MoViNet-A0<br/>violence classifier]
        CLIP[CLIP-ViT-B/32<br/>forensic embed]
    end

    subgraph Identity["Identity Service"]
        FAISS[(FAISS<br/>face + CLIP)]
        REID[Cross-cam<br/>Re-ID]
        FSM[Alert FSM]
        HEAD[HeadCount<br/>Aggregator]
        HOMO[Homography]
    end

    DB[(MSSQL Server)]
    DISP[Alert Dispatcher]
    SCHED[vms.scheduler]
    API[FastAPI + Socket.io]
    FE[React Frontend]

    Cameras --> Ingestion
    Ingestion -->|raw frame| SHM
    Ingestion -->|24-byte ptr| FS
    SHM -->|read| Inference
    FS --> Inference
    Inference --> DS
    DS --> Identity
    Identity --> TS
    Identity --> AS
    Identity --> DB
    DB <--> SCHED
    AS --> DISP
    DISP -->|email/slack/telegram/webhook| Channels[(External<br/>channels)]
    DB --> API
    API <-->|WebSocket| FE
    FE -->|corrections| API
    API --> CS
    CS --> Identity
```

**Key design decisions** (from `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` §3):

| Decision | Rationale |
|---|---|
| Shared memory for frames | Avoids sending raw pixels through Redis — only 24-byte metadata pointer per frame |
| Redis Streams over Pub/Sub | Persistence, consumer groups, replay, XAUTOCLAIM recovery |
| Process isolation for GPU | Python GIL never blocks API; OOM in inference doesn't kill API |
| Per-camera ByteTrack before Re-ID | Match confirmed tracklets, not noisy single detections |
| FAISS + zone adjacency pre-filter | Re-ID is O(n) per query, not O(n²) naive cosine |
| Trigger-gated heavy models | Violence runs only when ≥2 persons present; ~85% GPU cost reduction |

---

## Frame-to-alert data flow

The journey of one frame from camera to a fired alert, end-to-end:

```mermaid
sequenceDiagram
    autonumber
    participant Cam as Camera
    participant Ing as Ingestion Worker
    participant SHM as Shared Memory
    participant R as Redis Streams
    participant Inf as Inference Engine
    participant Id as Identity Service
    participant DB as MSSQL
    participant Dis as Dispatcher
    participant FE as Frontend

    Cam->>Ing: RTSP frame (1080p H.264)
    Ing->>SHM: write decoded BGR + 16B header
    Ing->>R: XADD frames:groupA {cam_id, shm_name, seq_id, ts}
    Inf->>R: XREADGROUP frames:groupA
    Inf->>SHM: read frame (validate seq_id + freshness <200ms)
    Inf->>Inf: SCRFD → faces + landmarks
    Inf->>Inf: YOLOv8 → persons
    Inf->>Inf: AdaFace → 512d embedding (gated on face)
    Inf->>Inf: ByteTrack → local_track_id
    alt persons >= 2 in frame
        Inf->>Inf: MoViNet violence (16-frame clip)
    end
    Inf->>R: XADD detections {cam_id, local_track_id, embedding, bbox, ts}
    Id->>R: XREADGROUP detections
    Id->>Id: FAISS query (zone-adjacency pre-filter)
    Id->>Id: assign global_track_id
    Id->>Id: homography → floor_x/y
    Id->>Id: AlertFSM evaluate
    alt suppressed by maintenance window
        Id->>DB: write alerts row state='suppressed'
    else dedup window passed and condition met
        Id->>DB: write alerts row state='active'
        Id->>R: XADD alerts {alert_id, type, severity, ts}
    end
    Id->>DB: batched tracking_events (MERGE on uq_tracking_idem)
    Dis->>R: XREADGROUP alerts
    Dis->>Dis: lookup alert_routing rules
    par fanout
        Dis->>FE: Socket.io alert_fired
    and
        Dis->>+Channels: email / slack / telegram / signed webhook
        Channels-->>-Dis: 200 / failure
    end
    Dis->>DB: alert_dispatches row (success/failure + retries)
```

---

## Anomaly detector pipeline

Every anomaly type implements the same `AnomalyDetector` interface. Adding theft, harassment, PPE, fall detection, etc. in v2.x is **one Python class plus one config row** — no architectural change.

```mermaid
flowchart TB
    Frame[Frame from Redis Streams] --> AlwaysOn{Always-on pool}
    AlwaysOn --> SCRFD[SCRFD face]
    AlwaysOn --> YOLO[YOLOv8n person]
    SCRFD --> Outputs[Inference Outputs]
    YOLO --> Outputs

    Outputs --> Reg[AnomalyDetector Registry]
    Reg --> Detectors{For each enabled detector}

    Detectors --> Unk["UNKNOWN_PERSON<br/>gate: tracklet w/o person_id"]
    Detectors --> Lost["PERSON_LOST<br/>gate: gtid absent everywhere"]
    Detectors --> Crowd["CROWD_DENSITY<br/>gate: zone count > capacity"]
    Detectors --> Intr["INTRUSION<br/>gate: restricted zone + outside hours"]
    Detectors --> Vio["VIOLENCE<br/>gate: persons in frame >= 2"]
    Detectors --> Loi["LOITERING<br/>gate: dwell > zone.loiter_threshold_s"]

    Unk --> FSM[Alert FSM]
    Lost --> FSM
    Crowd --> FSM
    Intr --> FSM
    Vio --> Heavy[Heavy model: MoViNet-A0]
    Heavy --> FSM
    Loi --> FSM

    FSM --> Maint{In maintenance window?}
    Maint -- yes --> Suppress[state='suppressed']
    Maint -- no --> Dedup{Dedup 60s/zone}
    Dedup -- pass --> Fire[state='active']
    Dedup -- block --> Drop[discard]

    Suppress --> DB[(MSSQL alerts)]
    Fire --> DB
    Fire --> RStream[Redis alerts stream]
```

**Detector matrix:**

| Type | Severity | Trigger gate | Sustained | Cooldown | Tier required |
|---|---|---|---|---|---|
| `UNKNOWN_PERSON` | HIGH | tracklet w/o person_id | >500ms | 60s/zone | FULL |
| `PERSON_LOST` | MEDIUM | gtid absent everywhere | >30s | 120s | FULL |
| `CROWD_DENSITY` | MEDIUM | count > zone.max_capacity | >10s | 300s/zone | FULL, MID |
| `INTRUSION` | CRITICAL | restricted zone + outside allowed_hours | >2s | 60s/zone | FULL, MID, LOW |
| `VIOLENCE` | CRITICAL | YOLO ≥2 persons → MoViNet conf > 0.65 | 2 consecutive clips | 30s/zone | FULL, MID |
| `LOITERING` | LOW | tracklet dwell > zone.loiter_threshold_s | continuous | 600s/zone | FULL, MID |

**Deferred to v2.x:** theft, harassment, PPE, fall detection, tampering — all addable as one new `AnomalyDetector` class each.

---

## Alert lifecycle

```mermaid
stateDiagram-v2
    [*] --> evaluating: detector emits candidate
    evaluating --> active: dedup pass + not suppressed
    evaluating --> suppressed: in maintenance window
    evaluating --> [*]: dedup blocked
    active --> acknowledged: operator acks
    active --> resolved: operator resolves directly
    acknowledged --> resolved: operator resolves
    suppressed --> [*]: archived
    resolved --> [*]: archived

    note right of suppressed
        Logged with suppressed_by_window_id
        Never delivered to channels
    end note

    note right of active
        Fanout: WebSocket + email + slack
        + telegram + webhook (per routing rules)
    end note
```

The four states (`active`, `acknowledged`, `resolved`, `suppressed`) are enforced by a CHECK constraint on `alerts.state`. Resolution timestamps must be non-decreasing (CHECK constraint `chk_alert_resolution_order`).

---

## Multi-channel alert delivery

When an alert fires, the dispatcher fans out to every channel matching the routing rules:

```mermaid
flowchart LR
    Alert[Alert fired<br/>Redis Stream] --> Disp[AlertDispatcher]
    Disp --> Lookup[(alert_routing<br/>matches type + severity + zone)]
    Lookup --> Fanout

    subgraph Fanout["For each matching rule"]
        WS[WebSocket<br/>Socket.io]
        Email[Email<br/>SMTP]
        Slack[Slack<br/>Web API]
        Tg[Telegram<br/>Bot API]
        Hook[Webhook<br/>HMAC-signed POST]
    end

    Fanout --> Audit[(alert_dispatches<br/>per-attempt audit)]
    Fanout --> Retry{Failure?}
    Retry -- yes --> Backoff[Exp backoff<br/>1s · 4s · 16s]
    Backoff --> Fanout
    Retry -- 3 fails --> DLQ[(dead_letter_dispatches)]
    DLQ --> AdminAlert[Admin alert]
```

Webhook payload is HMAC-SHA256 signed (`X-VMS-Signature` header). Customers verify with a shared secret. Mobile companion app deferred to v2.x.

---

## Camera capability tiering

The system **does not mandate a hardware floor.** At install time the `CameraProfiler` runs a 60-second probe and assigns each camera a tier; features are enabled per-camera based on tier. A signed PDF Site Readiness Report becomes the contractual baseline.

```mermaid
flowchart TD
    Start[Add camera] --> Probe[CameraProfiler 60s probe]
    Probe --> Measure[Measure: codec · resolution · actual fps · focus · lighting · encoder artefacts]
    Measure --> Decide{Capability decision}

    Decide -- ">=1080p AND >=12fps AND focus>=30" --> FullTier[FULL tier]
    Decide -- "720p-1080p OR 8-12fps OR focus 15-30" --> MidTier[MID tier]
    Decide -- "<720p OR <8fps OR analog OR focus<15" --> LowTier[LOW tier]

    FullTier --> FullFeats[All features<br/>face + anomaly + headcount + intrusion + violence + loitering<br/>SLA: 99% precision · less than 1.5s alert latency]
    MidTier --> MidFeats[Anomaly + headcount + intrusion + violence (best-effort)<br/>face recognition disabled per camera<br/>SLA: 90% recall · less than 3s alert latency]
    LowTier --> LowFeats[Headcount + intrusion only (zone rules)<br/>no deep-model features<br/>SLA: presence detection only]

    FullFeats --> Save[(cameras.capability_tier<br/>+ profile_data JSON)]
    MidFeats --> Save
    LowFeats --> Save
    Save --> PDF[Generate Site Readiness Report PDF<br/>Customer signs as contractual baseline]
```

---

## Database schema (key tables)

The full schema has 17 tables. Below are the most central entities and their relationships. See `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` §I and `docs/superpowers/specs/2026-05-01-vms-db-edge-cases.md` for the complete schema, CHECK constraints, and invariants.

```mermaid
erDiagram
    persons ||--o{ person_embeddings : "has"
    persons ||--o{ tracking_events : "appears in"
    cameras ||--o{ tracking_events : "captures"
    cameras ||--o{ alerts : "scoped to"
    zones ||--o{ zone_presence : "tracks dwell"
    zones ||--o{ maintenance_windows : "scoped"
    cameras ||--o{ maintenance_windows : "scoped"
    users ||--o{ alerts : "acknowledges"
    users ||--o{ maintenance_windows : "creates"
    users ||--o{ audit_log : "actor"
    alerts ||--o{ alert_dispatches : "delivered via"
    maintenance_windows ||--o{ alerts : "may suppress"
    anomaly_detectors }o--|| alerts : "produces type"
    cameras ||--o{ person_clip_embeddings : "captures"

    persons {
        int person_id PK
        string employee_id
        string full_name
        string person_type
        bool is_active
        datetime purged_at
    }
    cameras {
        int camera_id PK
        string name
        string rtsp_url
        string capability_tier "FULL/MID/LOW"
        text profile_data
        text model_overrides
    }
    zones {
        int zone_id PK
        string name
        text polygon
        int max_capacity
        bool is_restricted
        text allowed_hours
        int loiter_threshold_s
    }
    tracking_events {
        bigint event_id PK
        string global_track_id
        int person_id FK
        int camera_id FK
        int local_track_id
        datetime event_ts
        string idempotency "uq camera+local+ts"
    }
    alerts {
        int alert_id PK
        string state "active/ack/resolved/suppressed"
        string alert_type
        string severity
        int suppressed_by_window_id FK
    }
    maintenance_windows {
        int window_id PK
        string scope_type "CAMERA/ZONE"
        int scope_id
        string schedule_type "ONE_TIME/RECURRING"
        string cron_expr
    }
    anomaly_detectors {
        int detector_id PK
        string alert_type UK
        string class_path
        string model_version
    }
    audit_log {
        bigint audit_id PK
        string event_type
        string prev_hash "SHA-256 chain"
        string row_hash
    }
    person_clip_embeddings {
        bigint clip_emb_id PK
        string global_track_id
        bytes embedding "512f CLIP"
        string snapshot_path
    }
```

**Schema invariants** (excerpt from `db-edge-cases.md` §16):

- `tracking_events` idempotent on `(camera_id, local_track_id, event_ts)` (UNIQUE)
- `zone_presence.exited_at >= entered_at` (CHECK)
- `alerts` resolution timestamps non-decreasing: triggered ≤ acknowledged ≤ resolved (CHECK)
- `tracking_events.bbox_x2 > bbox_x1 AND bbox_y2 > bbox_y1` (CHECK)
- `audit_log.row_hash[N] == sha256(row_hash[N-1] || …fields…)` (app-enforced; verifiable via `GET /api/audit/verify`)
- FAISS active-vector count == DB active-embedding count (modulo 5; nightly drift check)

`tracking_events` is partitioned monthly via `pf_monthly` on MSSQL. Partitions older than 12 months are switched out to Parquet on object storage and dropped (see Scheduled Jobs §M).

---

## Deployment topology

The architecture supports horizontal scaling without a logic rewrite:

```mermaid
flowchart TB
    subgraph Single["Single GPU node — up to ~80 cameras"]
        S1[Cameras] --> S2[Ingestion + Inference + Identity + DB on one host]
        S2 --> S3[(MSSQL local)]
    end

    subgraph TwoNode["Two-node — ~80 to 200 cameras"]
        T1[Cameras subset A] --> TI1[Ingestion + Inference Node 1]
        T2[Cameras subset B] --> TI2[Ingestion + Inference Node 2]
        TI1 --> TR[(Redis Streams<br/>dedicated host)]
        TI2 --> TR
        TR --> TID[Identity Service]
        TID --> TD[(MSSQL)]
    end

    subgraph MultiSite["Multi-site / >200 cameras — v2.x"]
        M1[Site A complete deploy] --> MR[Redis -> Kafka migration<br/>same consumer-group API]
        M2[Site B complete deploy] --> MR
        MR --> MC[Central management instance<br/>alerts + tracking summaries only]
    end

    Single -.->|grow| TwoNode
    TwoNode -.->|migrate| MultiSite
```

**Capacity model** (full table in spec §G):

| GPU SKU | VRAM | Camera capacity at 1080p/15fps |
|---|---|---|
| RTX 4060 / A2000 | 8 GB | 10 – 15 |
| RTX 4090 / A4000 | 16 GB | 30 – 40 |
| RTX 6000 Ada / L40S | 48 GB | 80 – 100 |
| A100 / H100 | 40-80 GB | 150+ |

The architecture's "secret weapon" for scaling is shared-memory frame transport: doubling the camera count adds CPU but **does not double Redis bandwidth** because raw pixels never traverse the bus.

---

## Phase progression

```mermaid
gantt
    title VMS v2 Implementation Phases
    dateFormat YYYY-MM-DD
    axisFormat %b %Y

    section Phase 1
    1A · DB schema + scaffold      :p1a, 2026-05-01, 7d
    1B · Ingestion + inference + API stub :p1b, after p1a, 14d

    section Phase 2
    Identity + anomaly framework + maintenance :p2, after p1b, 21d

    section Phase 3
    CameraProfiler + dispatcher + audit + scheduler :p3, after p2, 14d

    section Phase 4
    Frontend (4A scaffold ... 4G a11y/perf) :p4, after p3, 35d

    section Phase 5
    Forensic CLIP search + production hardening :p5, after p4, 14d

    section Phase 6
    Camera rollout + customer pilot :p6, after p5, 21d
```

Each phase ships an independently testable deliverable. Phase 1A (current target) is detailed in `docs/superpowers/plans/2026-05-01-vms-v2-phase1a-db-schema.md` — 14 tasks, all TDD, ~1 week of work.

---

## Frontend architecture

```mermaid
flowchart TB
    App[App + Router + Providers] --> Login[/login]
    App --> Live[/live]
    App --> Analytics[/analytics]
    App --> Forensic[/forensic]
    App --> Admin[/admin]

    Live --> CG[CameraGrid]
    Live --> FC[FocusedCamera<br/>HLS + bbox overlay]
    Live --> AS[AlertSidebar]
    Live --> HC[HeadCountBanner]
    Live --> FP[FollowPersonPanel]

    Analytics --> TS[TimeScrubber]
    Analytics --> HM[FloorPlan + Heatmap]
    Analytics --> PP[PersonProfile]

    Forensic --> FS[Forensic CLIP Search]

    Admin --> EW[EnrolmentWizard]
    Admin --> HCal[HomographyCalibrator]
    Admin --> ZE[ZoneEditor]
    Admin --> MC[MaintenanceCalendar]
    Admin --> MM[ModelManager]
    Admin --> ALV[AuditLogViewer]

    subgraph State[Client + Server State]
        Z[(Zustand<br/>liveStore · authStore · themeStore)]
        TQ[(TanStack Query<br/>per-endpoint stale times)]
    end

    subgraph RealTime[Real-time]
        SocketIO[Socket.io client<br/>auto-reconnect + rehydrate]
    end

    Live -. uses .-> Z
    Live -. uses .-> SocketIO
    Analytics -. uses .-> TQ
    Forensic -. uses .-> TQ
    Admin -. uses .-> TQ
```

Full frontend spec: `docs/superpowers/specs/2026-05-01-vms-frontend-design.md`. Includes design tokens (dark + light themes), perf budgets (≤800kB initial bundle), WCAG 2.1 AA target, Vitest + Playwright test pyramid, and Phase 4 sub-plan decomposition.

---

## Tech stack

| Layer | Technology | Version |
|---|---|---|
| Face detection | SCRFD 2.5g (ONNX, CUDAExecutionProvider) | 1.0 |
| Face embedding | AdaFace IR50 (ONNX) | 1.0 |
| Person detection | YOLOv8n (ONNX, optional TensorRT) | 8.2 |
| Per-camera tracker | ByteTrack | bundled with ultralytics |
| Cross-camera Re-ID | FAISS flat IP index | 1.8 |
| Violence classifier | MoViNet-A0 trained on RWF-2000 | downloaded via manifest |
| Forensic embedding | CLIP-ViT-B/32 | downloaded via manifest |
| Message bus | Redis Streams (Kafka upgrade path at scale) | 5.x |
| IPC frames | `multiprocessing.shared_memory` | stdlib |
| Database | MSSQL Server (SQLAlchemy 2 + pyodbc) | 2019+ |
| Migrations | Alembic | 1.13 |
| Backend API | FastAPI + Uvicorn | 0.111 / 0.29 |
| Real-time | Socket.io (server + client) | 4 |
| Frontend | React 18 + TypeScript + Vite | 18 / 5.4 / 5 |
| Frontend styling | Tailwind CSS + shadcn/ui | 3.4 |
| Frontend maps | Leaflet + react-leaflet | 1.9 / 4 |
| Frontend video | HLS.js | 1.5 |
| Frontend testing | Vitest + RTL + Playwright | 1.6 / 16 / 1.44 |
| Process supervision | systemd (Linux) / NSSM (Windows) | n/a |
| Observability | Prometheus + Grafana | latest |

---

## Quick start

> **Phase 1A** is the current implementation target. Until Phase 1B lands, the system has DB + scaffold only — no live pipeline yet. The legacy webcam prototype files (`main.py`, `face_detection.py`, etc.) are kept as reference and will be removed in Phase 1B.

### Prerequisites

- Python 3.11
- MSSQL Server 2019+ (Express works for dev) — connection string with ODBC Driver 17
- Redis 5+ (for Phase 1B onward)
- NVIDIA GPU with CUDA 12 (for Phase 1B+ inference; CPU fallback supported)

### Set up the development environment

```powershell
# Windows (project's primary dev OS)
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -U pip
pip install -r requirements.txt -r requirements-dev.txt
```

### Configure

Create `.env` at repo root (gitignored):

```
VMS_DB_URL=mssql+pyodbc://USER:PASS@HOST/vms_dev?driver=ODBC+Driver+17+for+SQL+Server
VMS_REDIS_URL=redis://localhost:6379/0
VMS_JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">
VMS_AT_REST_KEY=<generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">
```

### Apply database migrations

```powershell
alembic upgrade head
```

### Run the test suite

```powershell
pytest -v
pytest --cov=vms --cov-report=term-missing  # with coverage
```

### Lint, format, type-check

```powershell
black vms/ tests/
ruff check vms/ tests/
mypy vms/
```

### Download ML models *(Phase 1B onward)*

```powershell
vms-models download   # fetches all required ONNX models from manifest, SHA-256 verified
vms-models verify
vms-models list
```

---

## Repository layout

```
.
├── vms/                                  # Production Python package
│   ├── config.py                         # pydantic-settings; env vars VMS_*
│   ├── db/
│   │   ├── session.py                    # engine, Base, SessionLocal, get_db
│   │   ├── models.py                     # 17 ORM models
│   │   └── audit.py                      # hash-chain writer (write_audit_event)
│   ├── ingestion/                        # Phase 1B
│   ├── inference/                        # Phase 1B
│   ├── identity/                         # Phase 2 — re-id, FAISS, FSM, HeadCountAggregator
│   ├── anomaly/                          # Phase 2 — AnomalyDetector + concrete detectors
│   ├── dispatcher/                       # Phase 3 — multi-channel alert delivery
│   ├── profiler/                         # Phase 3 — CameraProfiler + Site Readiness Report
│   ├── scheduler/                        # Phase 3 — cron orchestrator
│   ├── api/                              # FastAPI routes + WebSocket
│   └── security/                         # JWT, at-rest cipher
│
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 0001_initial_schema.py        # full v2 schema, dialect-gated MSSQL extras
│
├── frontend/                             # Phase 4 — React SPA
│   ├── src/
│   │   ├── shared/                       # design system, api client, auth
│   │   └── features/
│   │       ├── live/                     # Guard view
│   │       ├── analytics/                # Management view
│   │       ├── forensic/                 # CLIP search
│   │       └── admin/                    # Admin views
│   └── ...
│
├── models/                               # Downloaded ONNX (gitignored); manifest committed
│   └── manifest.json
│
├── docs/
│   ├── superpowers/
│   │   ├── specs/
│   │   │   ├── 2026-04-23-vms-facial-recognition-design.md   # v1
│   │   │   ├── 2026-05-01-vms-v2-hardened-design.md          # v2 (authoritative)
│   │   │   ├── 2026-05-01-vms-db-edge-cases.md               # v2 companion
│   │   │   └── 2026-05-01-vms-frontend-design.md             # v2 companion
│   │   └── plans/
│   │       ├── 2026-04-23-phase1-foundation.md               # superseded
│   │       └── 2026-05-01-vms-v2-phase1a-db-schema.md        # current target
│   ├── presentation/                     # browser presentation for stakeholders
│   └── EXPLAINER.md                      # plain-language overview
│
├── tests/                                # Pytest suite mirroring vms/ structure
├── scripts/                              # CLI tools, fine-tune recipes (Phase 5)
│
├── CLAUDE.md                             # AI-driven development rules
├── README.md                             # this file
├── pyproject.toml                        # black/ruff/mypy/pytest config
├── requirements.txt
└── requirements-dev.txt
```

Legacy prototype files at the repo root (`main.py`, `face_detection.py`, `enrollment_emp.py`, `face_utils.py`, `scrfd_face.py`, `test.py`, `test_db.py`, `config.py`) are kept as reference until Phase 1B replaces them. **Do not import from them.**

---

## Documentation map

```mermaid
flowchart LR
    R[README.md<br/>this file] --> CL[CLAUDE.md<br/>AI dev rules]
    R --> EX[docs/EXPLAINER.md<br/>stakeholder overview]
    R --> V2[v2 hardened spec<br/>SOURCE OF TRUTH]

    V2 --> EC[DB edge-cases spec]
    V2 --> FE[Frontend spec]
    V2 --> P1A[Phase 1A plan<br/>current target]

    EC -.constrains.-> P1A
    FE -.constrains.-> P4[Phase 4 plans<br/>future]
    V2 -.constrains.-> P1B[Phase 1B+ plans<br/>future]

    style V2 fill:#fef3c7,stroke:#92400e
    style P1A fill:#dbeafe,stroke:#1e40af
```

| Document | Read when |
|---|---|
| [CLAUDE.md](./CLAUDE.md) | Before any code change — encodes git rules, security boundaries, conventions |
| [v2 hardened spec](./docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md) | Before designing or implementing any feature |
| [DB edge-cases spec](./docs/superpowers/specs/2026-05-01-vms-db-edge-cases.md) | Before any DB change or new constraint |
| [Frontend design spec](./docs/superpowers/specs/2026-05-01-vms-frontend-design.md) | Before any UI work |
| [Phase 1A plan](./docs/superpowers/plans/2026-05-01-vms-v2-phase1a-db-schema.md) | When implementing the current phase |
| [v1 spec](./docs/superpowers/specs/2026-04-23-vms-facial-recognition-design.md) | For sections marked "unchanged" in v2 |
| [EXPLAINER](./docs/EXPLAINER.md) | When briefing non-technical stakeholders |

---

## Testing

The project enforces TDD on every task. Tests are co-located by feature and run on every commit.

### Coverage targets

| Module | Target |
|---|---|
| `vms/db`, `vms/config`, `vms/anomaly`, `vms/dispatcher`, `vms/security` | ≥ 80% |
| `vms/identity`, `vms/api`, `vms/inference` | ≥ 75% |
| Other | ≥ 70% |

### Test types

| Type | Tool | Run | Marker |
|---|---|---|---|
| Unit | Vitest / pytest | every commit | (default) |
| Integration | pytest | on `main` branch | `@pytest.mark.integration` |
| E2E (frontend) | Playwright | on `main` branch | n/a |
| Migration round-trip | pytest + alembic | every commit (SQLite) + on `main` (MSSQL) | n/a |
| Accessibility | axe-core | every commit | n/a |
| Performance budget | Lighthouse + bundle analyser | every commit | n/a |

### Definition of done

A task is done when **all** of: tests pass, lint clean, format applied, mypy clean, coverage at target, schema migrations round-trip, conventional commit created, plan checkbox marked.

Full checklist in [`CLAUDE.md` §11](./CLAUDE.md#11-definition-of-done).

---

## Operations

### Scheduled jobs (Phase 3+)

The `vms.scheduler` process runs 12 production cron jobs (full list in spec §M):

| Critical jobs | Cadence |
|---|---|
| `partition_create_next_month` | 25th of each month, 02:00 |
| `archive_old_partitions` | Daily 03:00 |
| `audit_chain_verify` | Daily 05:00 (CRITICAL on broken chain) |
| `faiss_drift_check` | Daily 05:30 |
| `worker_heartbeat_check` | Every 10s |
| `maintenance_calendar_refresh` | Every 30s |

### Disaster recovery

- **RPO:** 15 min (production); 5 min during high-risk windows
- **RTO:** 1 hour (production)
- **DR drill:** quarterly — restore latest backup + tlog to a parallel instance, run audit verify, run `vms-doctor` self-test

Full runbook: [`db-edge-cases.md` §9](./docs/superpowers/specs/2026-05-01-vms-db-edge-cases.md#9-backup-restore-disaster-recovery).

### Security boundaries

- All API endpoints authenticated via JWT (8h expiry); role-based + zone/camera-level checks on every request
- Face embeddings encrypted at rest (Fernet; key in env / Windows DPAPI)
- RTSP credentials never logged at INFO; treated as secrets
- GDPR `DELETE /api/persons/{id}` blanks embeddings and scrubs thumbnails — irreversible, audit-logged
- Audit log is immutable hash-chain — `GET /api/audit/verify` walks the chain on demand

Full security policy: [`CLAUDE.md` §7](./CLAUDE.md#7-security-boundaries--never-cross-these).

---

## Contributing

Read [`CLAUDE.md`](./CLAUDE.md) before opening a PR. The project enforces:

- Conventional commit messages (`feat:`, `fix:`, `refactor:`, etc.) with no AI co-author footer
- Black + Ruff + Mypy clean on every change
- TDD for every feature task — failing test, implementation, passing test, commit
- Schema changes ship as Alembic migrations in the same commit as the model change
- No reset --hard, no checkout --, no clean -fd in any branch (see `CLAUDE.md` §9)

Branch + PR workflow:

```powershell
git checkout -b feat/your-feature
# ... TDD cycle ...
git push -u origin feat/your-feature
gh pr create --title "feat: your feature" --body "..."
```

---

## License

Proprietary — APL Techno. Internal product.

---

*Built for plant security and operations management. Stack: Python 3.11 · FastAPI · React 18 · MSSQL · Redis · ONNX · FAISS.*
