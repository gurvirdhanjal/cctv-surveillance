# VMS v2 — Hardened Design (Existing-Camera Retrofit + Anomaly Suite + Maintenance + Scaling)

**Design Specification** · 2026-05-01
**Status:** Approved · Supersedes the v1 baseline for in-scope sections; v1 sections marked *unchanged* below remain authoritative.
**Supersedes (in part):** `docs/superpowers/specs/2026-04-23-vms-facial-recognition-design.md`

---

## Changelog v1 → v2 — one-page summary

| Area | v1 baseline | v2 hardened |
|---|---|---|
| Sales positioning | Spec assumed new cameras procured to recommended spec | Existing IP cameras are the **default deployment**; smart cameras are an optional upgrade. Camera floor replaced with **per-camera capability tiering** at install time |
| Anomaly alerts | UNKNOWN_PERSON, PERSON_LOST, CROWD_DENSITY | + INTRUSION, VIOLENCE, LOITERING. Theft/harassment deferred to v2.x. All anomalies implement a pluggable `AnomalyDetector` interface — adding new anomaly types is one Python class + one config row |
| Heavy-model execution | All models always-on per camera | **Trigger-gated**: violence runs only when YOLO sees ≥2 persons; loitering runs only on tracklets exceeding dwell threshold; intrusion is a free zone+time rule |
| Maintenance windows | Not specified | Per-camera + per-zone, recurring (cron) or one-time. Suppressed alerts are logged with `state='suppressed'` for audit |
| Alert delivery | WebSocket only | + Email (SMTP), Slack, Telegram, signed outbound webhook. Mobile companion app deferred to v2.x |
| Camera diagnostics | Manual setup | Install-time `CameraProfiler` runs a 60-second probe, classifies into FULL/MID/LOW capability tier, generates a signed PDF site-readiness report |
| Forensic search | Not in scope | CLIP-based text-to-clip search across the last 30 days |
| Audit log | Not in scope | Immutable append-only `audit_log` with hash-chain tamper detection |
| Capacity planning | "Multi-node upgrade path" mentioned | Concrete per-GPU-SKU capacity table + 3-step scaling runbook (single-GPU → two-node → Kafka) |
| Production hardening | Implicit | 12 explicit failure modes covered (clock skew, embedding drift, GDPR erasure, anti-spoofing hook, model rollback, privacy-at-rest, etc.) |
| Theft / harassment / mobile app / SaaS / PPE / shift emails / klaxon / CAD heatmap / tampering detection | — | All explicitly **deferred to v2.x** to keep v1 shippable |

---

## §A. Scope (replaces v1 §1)

### v1 In-scope (locked)

1. Face detection, recognition, cross-camera tracking *(unchanged from v1 §6–§8)*
2. **Head count** per zone and plant-wide as a first-class API + UI deliverable
3. Anomaly alerts:
   - Existing: `UNKNOWN_PERSON`, `PERSON_LOST`, `CROWD_DENSITY`
   - New: `INTRUSION`, `VIOLENCE`, `LOITERING`
4. **Per-camera capability tiering** (FULL / MID / LOW) detected at install time
5. **Maintenance windows** — per-camera + per-zone, recurring + one-time
6. **Multi-channel alert delivery** — WebSocket, email (SMTP), Slack, Telegram, outbound webhook
7. **Camera health auto-diagnostics** + signed PDF site-readiness report
8. **Forensic search** via CLIP embeddings (text query → matching clips, 30-day window)
9. **Audit-grade immutable event log** with hash-chain
10. Floor-plan homography, zone analytics, dwell time, timeline playback, enrolment, RBAC, observability, degraded mode *(all unchanged from v1)*

### Deferred to v2.x

- Theft detection (high false-positive risk; needs customer-specific tuning)
- Harassment detection (action recognition immaturity)
- Mobile companion app
- Multi-tenant SaaS variant
- PPE compliance (helmet/vest)
- Plant-floor klaxon / GPIO relay output
- CAD heatmap export
- Shift-end auto-email reports
- Camera tampering detection
- On-camera (smart camera) edge inference offload

### Non-negotiable design principle

**Every anomaly type implements the same interface.** Adding a new anomaly type in v2.x = one Python class + one row in `anomaly_detectors` config. The pipeline, FSM, dispatcher, and UI never change.

---

## §B. Existing-camera retrofit + tiered capability *(replaces v1 §17)*

### Sales positioning

The product is sold as **"works on your existing IP cameras."** Smart cameras are optional — presented as an upgrade with concrete benefits (lower GPU cost, edge inference offload, planned for v2.x). The system no longer mandates a hardware floor.

### CameraProfiler — install-time probe

A new module runs at camera registration and on demand:

| Probe step | What it measures |
|---|---|
| RTSP negotiate | Protocol version, transport (TCP/UDP), credentials valid |
| Stream metadata | Codec (H.264 / H.265 / MJPEG), declared resolution, declared fps |
| Live measurement (60s) | Actual decoded fps, frame drop rate, packet loss |
| Frame-quality sample (30 frames) | Laplacian variance (focus), brightness histogram (lighting), motion baseline |
| Encoder-artefact scan | Detects analog-via-encoder (deinterlace combing) — flags as LOW tier |
| Night-mode probe | If camera supports `ONVIF.day_night`, requests IR mode and re-samples brightness |

### Capability tiers

| Tier | Conditions | Features enabled | SLA |
|---|---|---|---|
| `FULL` | ≥1080p @ ≥12 fps measured, focus_score ≥30 | Face recognition + anomaly + head count + intrusion + violence + loitering | 99% precision on identity; <1.5s alert latency |
| `MID` | 720p–1080p **OR** 8–12 fps **OR** focus 15–30 | Anomaly + head count + intrusion + violence (best-effort). Face recognition disabled per-camera | 90% recall on persons; <3s alert latency |
| `LOW` | <720p **OR** <8 fps **OR** analog-via-encoder **OR** focus <15 | Head count + intrusion only (zone-based rules). No deep-model features | "presence detection only" |

### Site Readiness Report (Sales Asset A)

After profiling all cameras, the system generates a one-page PDF:
- Per-camera row: tier, measured properties, sample frame thumbnail, features enabled, *why this tier*
- Customer signature block at the bottom
- Becomes the documented contractual baseline for what the system promises at this site

### DB additions

```sql
ALTER TABLE cameras ADD capability_tier NVARCHAR(10) NOT NULL DEFAULT 'FULL';
ALTER TABLE cameras ADD profile_data NVARCHAR(MAX) NULL;     -- JSON of measured properties
ALTER TABLE cameras ADD profiled_at DATETIME2 NULL;
ALTER TABLE cameras ADD CONSTRAINT chk_camera_tier
    CHECK (capability_tier IN ('FULL', 'MID', 'LOW'));
```

### API

```
POST   /api/cameras/{id}/profile               # re-runs profiler; useful when a camera is replaced
GET    /api/cameras/{id}/profile               # returns last profile data + tier reason
GET    /api/sites/readiness-report.pdf?site=  # generates signed PDF
```

---

## §C. Anomaly framework *(replaces v1 §9)*

### `AnomalyDetector` interface

```python
class AnomalyDetector(ABC):
    alert_type: str                  # e.g. "VIOLENCE"
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    requires_models: list[str]       # ["yolo_person", "violence_classifier"]
    requires_tier: list[str]         # ["FULL", "MID"] — tier gate

    @abstractmethod
    def should_run(self, frame_meta: FrameMeta, prior_outputs: dict) -> bool:
        """Trigger gate. Return False to skip on this frame."""

    @abstractmethod
    def evaluate(self, frame: np.ndarray, prior_outputs: dict) -> AnomalyEvent | None:
        """Run model + emit candidate event."""

    @abstractmethod
    def fsm_config(self) -> FSMConfig:
        """Sustain duration, cooldown, dedup window, severity escalation rules."""
```

Adding theft / harassment / PPE / fall detection in v2.x = one new class + one row in `anomaly_detectors`. **Core architecture never changes.**

### Detector registry (DB)

```sql
CREATE TABLE anomaly_detectors (
    detector_id        INT IDENTITY PRIMARY KEY,
    alert_type         NVARCHAR(30) NOT NULL UNIQUE,
    class_path         NVARCHAR(200) NOT NULL,    -- e.g. "vms.anomaly.violence.ViolenceDetector"
    is_enabled         BIT NOT NULL DEFAULT 1,
    config_json        NVARCHAR(MAX) NULL,        -- detector-specific tuning (thresholds, etc.)
    model_version      NVARCHAR(50) NULL,         -- for canary / rollback
    created_at         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
```

### v1 detector matrix

| `alert_type` | Model / mechanism | Trigger gate | Sustained | Cooldown | Severity | Tier required |
|---|---|---|---|---|---|---|
| `UNKNOWN_PERSON` | Existing pipeline | Person tracklet without `person_id` | >500ms in frame | 60s/zone | HIGH | FULL |
| `PERSON_LOST` | Tracker state | `global_track_id` absent everywhere | >30s | 120s | MEDIUM | FULL |
| `CROWD_DENSITY` | YOLO count + zone | `count > zone.max_capacity` | >10s continuous | 300s/zone | MEDIUM | FULL, MID |
| `INTRUSION` | YOLO + zone + schedule | Person enters `is_restricted=true` zone outside `zones.allowed_hours` | >2s | 60s/zone | CRITICAL | FULL, MID, LOW |
| `VIOLENCE` | MoViNet-A0 (ONNX, pre-trained on RWF-2000) | YOLO sees ≥2 persons in frame; run model on rolling 16-frame clip every 1s | confidence >0.65 sustained over 2 consecutive clips | 30s/zone | CRITICAL | FULL, MID |
| `LOITERING` | Tracker dwell | Single tracklet in zone >`zones.loiter_threshold_s` (default 180s) | continuous | 600s/zone | LOW | FULL, MID |

### Trigger-gated execution

The `InferenceEngine` separates models into two pools:

- **Always-on pool:** SCRFD (face), YOLOv8n (person). Run on every frame at the camera's configured fps.
- **Gated pool:** AdaFace (only on faces ≥`MIN_FACE_PX`), MoViNet violence (only when YOLO output passes the gate condition for that camera/frame).

Gate predicates run in a CPU-side rule layer between model passes — cost ~0ms. The framework calls `should_run()` on every detector before invoking `evaluate()`.

### Zone schedule additions

```sql
ALTER TABLE zones ADD allowed_hours NVARCHAR(MAX) NULL;       -- JSON cron-windows when persons are allowed
ALTER TABLE zones ADD loiter_threshold_s INT NOT NULL DEFAULT 180;
```

`allowed_hours` example: `[{"days":[1,2,3,4,5],"start":"08:00","end":"18:00"}]` — Mon-Fri working hours. A person in the zone outside these hours triggers `INTRUSION`.

---

## §D. Maintenance windows *(NEW — full new section)*

### DB schema

```sql
CREATE TABLE maintenance_windows (
    window_id            INT IDENTITY PRIMARY KEY,
    name                 NVARCHAR(200) NOT NULL,
    scope_type           NVARCHAR(20) NOT NULL,        -- 'CAMERA' | 'ZONE'
    scope_id             INT NOT NULL,                 -- FK to cameras OR zones depending on scope_type
    schedule_type        NVARCHAR(20) NOT NULL,        -- 'ONE_TIME' | 'RECURRING'
    starts_at            DATETIME2 NULL,               -- ONE_TIME only
    ends_at              DATETIME2 NULL,               -- ONE_TIME only
    cron_expr            NVARCHAR(100) NULL,           -- RECURRING: e.g. '0 14 * * 6' (Sat 2pm)
    duration_minutes     INT NULL,                     -- RECURRING: window length
    suppress_alert_types NVARCHAR(MAX) NULL,           -- NULL = suppress ALL types; else JSON array
    is_active            BIT NOT NULL DEFAULT 1,
    reason               NVARCHAR(500) NULL,           -- audit trail
    created_by           INT NOT NULL,
    created_at           DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT chk_mw_scope CHECK (scope_type IN ('CAMERA', 'ZONE')),
    CONSTRAINT chk_mw_sched CHECK (schedule_type IN ('ONE_TIME', 'RECURRING')),
    CONSTRAINT chk_mw_one_time
        CHECK (schedule_type <> 'ONE_TIME' OR (starts_at IS NOT NULL AND ends_at IS NOT NULL)),
    CONSTRAINT chk_mw_recurring
        CHECK (schedule_type <> 'RECURRING' OR (cron_expr IS NOT NULL AND duration_minutes IS NOT NULL))
);

CREATE INDEX idx_mw_active_scope
    ON maintenance_windows (scope_type, scope_id) WHERE is_active = 1;
```

### Suppression logic

Before any alert fires, `AlertFSM` checks `MaintenanceCalendar.is_suppressed(camera_id, zone_id, alert_type, event_ts)`.

The calendar caches active windows in memory, refreshed every 30s (or invalidated on `POST/PATCH/DELETE` to maintenance API). Suppressed alerts are **logged but not delivered**:

```sql
ALTER TABLE alerts ADD suppressed_by_window_id INT NULL FK maintenance_windows;
-- alerts.state already supports values 'active', 'acknowledged', 'resolved' — add 'suppressed'
```

This preserves auditability ("we knew, it was scheduled").

### "Camera offline — was this expected?" distinction

| Camera state × Maintenance state | Behaviour |
|---|---|
| Camera offline + active window | No admin alert. Status badge: **"scheduled maintenance"** |
| Camera offline + no window | Existing HIGH alert path |
| Camera online + active window | Admin warning: "expected down but online — typo in schedule?" — non-blocking |
| Camera online + no window | Normal operation |

### API

```
POST    /api/maintenance                      # create window
GET     /api/maintenance?scope_type=&scope_id=&active=true
PATCH   /api/maintenance/{id}                 # edit (cancellation creates audit log entry)
DELETE  /api/maintenance/{id}                 # soft-delete (sets is_active=0)
GET     /api/maintenance/calendar?from=&to=   # Gantt-friendly view for admin UI
```

### Frontend (admin)

Calendar widget on the Admin view: monthly Gantt chart of all upcoming windows colour-coded by scope, with quick-add and edit dialogs. Conflict warning when overlapping windows are created.

---

## §E. Multi-channel alert delivery *(NEW — extends v1 §13 WebSocket)*

### `AlertDispatcher` process

A new dedicated process reads from the `alerts` Redis Stream. For each alert, it evaluates `alert_routing` and fans out to every matching channel.

| Channel | Implementation | Notes |
|---|---|---|
| `WEBSOCKET` | Existing `alert_fired` event | unchanged from v1 |
| `EMAIL` | SMTP — host configurable per deployment (Postfix relay or external SMTP) | HTML email with snapshot inline |
| `SLACK` | Bot user, posts to channel via Slack Web API | Channel mapped per zone or per alert type |
| `TELEGRAM` | Bot API `sendMessage` | Group chat ID mapped per customer |
| `WEBHOOK` | Outbound HTTPS POST, signed with HMAC-SHA256 | Customer's PSIM, alarm panel, or Zapier-style integration |

### Idempotency & retries

```sql
CREATE TABLE alert_dispatches (
    dispatch_id    BIGINT IDENTITY PRIMARY KEY,
    alert_id       INT NOT NULL FK alerts,
    channel        NVARCHAR(20) NOT NULL,
    target         NVARCHAR(500) NOT NULL,
    attempt_n      INT NOT NULL DEFAULT 1,
    dispatched_at  DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    success        BIT NOT NULL,
    error          NVARCHAR(MAX) NULL,
    response_code  INT NULL                     -- HTTP status for webhook; null for others
);
CREATE INDEX idx_dispatches_alert ON alert_dispatches (alert_id);
```

Retries use exponential backoff (1s, 4s, 16s) up to 3 attempts. Persistent failures move to `dead_letter_dispatches` and emit an admin alert.

### Routing rules

```sql
CREATE TABLE alert_routing (
    routing_id   INT IDENTITY PRIMARY KEY,
    alert_type   NVARCHAR(30) NULL,             -- NULL = all types
    severity     NVARCHAR(10) NULL,             -- NULL = all severities
    zone_id      INT NULL,                      -- NULL = all zones
    channel      NVARCHAR(20) NOT NULL,
    target       NVARCHAR(500) NOT NULL,        -- email | slack channel | tg chat_id | webhook URL
    is_active    BIT NOT NULL DEFAULT 1,
    CONSTRAINT chk_routing_channel
        CHECK (channel IN ('EMAIL','SLACK','TELEGRAM','WEBHOOK','WEBSOCKET'))
);
```

A single alert can match multiple rules (e.g. CRITICAL alerts route to both Slack and webhook).

### Webhook payload

```json
{
  "alert_id": 12345,
  "alert_type": "VIOLENCE",
  "severity": "CRITICAL",
  "camera_id": 7,
  "camera_name": "Loading Bay 2",
  "zone_id": 3,
  "zone_name": "Loading Bay",
  "triggered_at": "2026-05-01T14:32:11.123Z",
  "snapshot_url": "https://vms.example.com/api/alerts/12345/snapshot.jpg",
  "snapshot_jwt": "eyJhbGciOi...",                 // 5-min signed token; downstream system uses this to fetch
  "global_track_id": "8f42...",
  "person_id": null,
  "schema_version": "1"
}
```

Header: `X-VMS-Signature: sha256=<hmac>` — customer verifies with shared secret.

---

## §F. Sales features

### F.1 Camera health auto-diagnostics *(integrated with §B)*

CameraProfiler outputs the **Site Readiness Report** PDF — see §B. Key sales asset because it sets contractual expectations *before* the customer says "your software doesn't work" later.

### F.2 Forensic CLIP search

CLIP-ViT-B/32 (ONNX, runs on the same GPU) computes a 512-dim embedding for every detected person crop, in addition to the AdaFace face embedding. Stored in `person_clip_embeddings` and indexed in a dedicated FAISS index.

```sql
CREATE TABLE person_clip_embeddings (
    clip_emb_id      BIGINT IDENTITY PRIMARY KEY,
    global_track_id  UNIQUEIDENTIFIER NOT NULL,
    camera_id        INT NOT NULL,
    event_ts         DATETIME2(3) NOT NULL,
    embedding        VARBINARY(2048) NOT NULL,    -- 512 float32
    snapshot_path    NVARCHAR(500) NOT NULL       -- path to crop on disk
);
CREATE INDEX idx_clip_ts ON person_clip_embeddings (event_ts DESC);
```

#### API

```
GET /api/forensic/search?q=person+in+red+shirt&from=&to=&zone_id=
→ {
    "matches": [
       {"event_ts": "...", "camera_id": 4, "global_track_id": "...",
        "snapshot_url": "...", "score": 0.83, "clip_url": "/api/forensic/clips/..."},
       ...
    ]
}
```

Server pre-computes the CLIP text-encoder embedding for the query, runs cosine search against `person_clip_embeddings` within the time window, returns ranked clips. Sub-second responses for 30-day windows on indexed data.

#### Cost

Adds ~10ms/inference per detected person crop. Trigger-gated to skip when fewer than 1 face/sec detected. Storage: ~200 bytes/crop × 1M crops/month ≈ 200MB/month — manageable.

### F.3 Audit-grade immutable event log

```sql
CREATE TABLE audit_log (
    audit_id     BIGINT IDENTITY PRIMARY KEY,
    event_type   NVARCHAR(50) NOT NULL,           -- 'ALERT_FIRED' | 'OPERATOR_ACK' | 'PERSON_ENROLLED' | etc.
    actor_user_id INT NULL,                       -- NULL = system event
    target_type  NVARCHAR(50) NULL,
    target_id    NVARCHAR(50) NULL,
    payload      NVARCHAR(MAX) NULL,              -- JSON event details
    prev_hash    CHAR(64) NOT NULL,
    row_hash     CHAR(64) NOT NULL,
    event_ts     DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE INDEX idx_audit_ts ON audit_log (event_ts DESC);
CREATE INDEX idx_audit_target ON audit_log (target_type, target_id, event_ts DESC);
```

Hash-chain: `row_hash = SHA-256(prev_hash || event_type || actor_user_id || target_type || target_id || payload || event_ts)`. The first row uses a sentinel `prev_hash = '0' * 64`.

#### Tracked events

- Every alert fired, acknowledged, resolved, suppressed
- Every operator action: enrolment, calibration, zone edit, identity correction, maintenance window CRUD
- Every config change: routing rule, anomaly detector enable/disable, threshold change
- Every login (success and failure)

#### Verification

```
GET  /api/audit/verify?from=&to=
→ { "rows_checked": 12345, "broken_chain_at": null }
GET  /api/audit/export?from=&to=&format=pdf  # signed PDF for compliance audits
```

A scheduled job runs `verify` daily and emits a CRITICAL alert on any broken link.

---

## §G. Capacity model & scaling runbook *(replaces v1 §3 Multi-Node Upgrade Path)*

### Three independent bottlenecks

#### G.1 RTSP decode (CPU-bound)

```
Per camera @ 1080p/15fps H.264, software decode  : ~0.07 CPU cores
1 modern Xeon core decodes                       : ~13 cameras
With NVDEC enabled                               : ~30+ cameras per process
                                                   (decode moves to GPU video engine,
                                                    separate hardware unit from CUDA cores)
```

Adding cameras adds CPU load linearly. 4 ingestion workers × 13 cams = 52 cams comfortably. Beyond 100 cams: enable NVDEC or add ingestion hosts.

#### G.2 GPU inference (the real ceiling)

```
Total budget = Σ (cameras × fps × model_cost)

Per-camera GPU time @ 15fps with trigger-gated heavy models:
  SCRFD (face)          : 15 fps × 6 ms    =  90 ms/sec/cam
  AdaFace (embed)       :  5 fps × 4 ms    =  20 ms/sec/cam   (only on detected faces)
  YOLOv8n (person)      : 15 fps × 4 ms    =  60 ms/sec/cam
  CLIP (forensic)       :  2 fps × 5 ms    =  10 ms/sec/cam   (only on detected persons)
  Intrusion rule        : ~0 (CPU-side)
  Violence (gated)      :  5 fps × 25 ms   = 125 ms/sec/cam   (only when ≥2 persons; ~30% of frames in normal ops)
  Loitering (gated)     : negligible (re-uses YOLO + tracker)

Per-camera GPU steady-state ≈ 200-300 ms/sec → ≈ 25-30% utilisation per camera
```

#### G.3 GPU SKU capacity at 1080p / 15fps

| GPU | VRAM | Camera capacity | Indicative cost (₹) |
|---|---|---|---|
| RTX 4060 / A2000 | 8 GB | 10 – 15 | ~80k |
| RTX 4090 / A4000 | 16 GB | 30 – 40 | ~2.5L |
| RTX 6000 Ada / L40S | 48 GB | 80 – 100 | ~6L |
| A100 / H100 | 40-80 GB | 150+ | ~10L+ |

The 52-camera plant fits **one A4000-class GPU** comfortably with headroom for v2.x additions. For >80 cameras, add a second GPU server rather than buying a larger one — cheaper and adds redundancy.

#### G.4 DB writes — negligible at v1 scale

52 cams × 15 fps × ~3 detections/frame = ~2,300 rows/sec → well within MSSQL's batched-write capacity (500ms/100-row flush already specced).

### Scaling runbook — "add 50 more cameras"

1. **Up to ~80 cameras (single GPU server)**
   - Add ingestion worker processes; partition cameras across workers via `cameras.worker_group`.
   - No GPU change needed if running A4000+.
   - No code change.

2. **80 → 200 cameras (two-node)**
   - Stand up a second GPU host.
   - Move Redis to its own machine (becomes shared message bus).
   - Each GPU node runs its own `InferenceEngine`, consuming a partition of `frames:groupX` Redis Streams.
   - `IdentityService` stays single (it's not GPU-bound) — receives detections from all nodes.
   - `DBWriter` scales out trivially: each writer commits its own partition.
   - Documented as the **"two-node deploy"** in production runbook.

3. **200+ cameras (multi-tenant or multi-site)**
   - Swap Redis Streams for **Kafka** — same consumer-group API shape, no logic rewrite.
   - Shard `IdentityService` by zone-cluster.
   - Multi-site: each site is a self-contained deployment that ships only alerts + tracking summaries to a central management instance.

### Why doubling cameras doesn't double Redis load

The shared-memory frame transport is the architecture's "secret weapon." Redis carries only 24-byte frame pointers; raw pixels never traverse the bus. Adding cameras adds ingestion CPU but not message-bus bandwidth.

---

## §H. Hardening additions *(NEW — addresses production failure modes the v1 spec missed)*

| # | Failure mode | v1 coverage | v2 hardening |
|---|---|---|---|
| H1 | Identity service crash mid-tracking | Implicit restart | Persist last-known-state (`global_track_id` ↔ `(camera_id, local_track_id, embedding)`) to Redis hash every 5s. On restart: rebuild from snapshot + replay last 5 min of `tracking_events` |
| H2 | NTP / clock skew between cameras | Not mentioned | Each event carries `ingest_ts` (worker clock) **and** `event_ts` (frame timestamp). Identity service rejects events with skew > 30s; emits admin alert on persistent skew. Production runbook requires NTP client on all hosts |
| H3 | Camera replaced in-place | Not mentioned | `POST /api/cameras/{id}/recalibrate-required` invalidates homography + capability tier, flags camera for re-profiling. `floor_x/y` go NULL until re-calibrated |
| H4 | Embedding drift (employee changes appearance) | Not mentioned | When a known person matches at sim 0.72–0.85 (low-confidence band) for >50 events, surface in admin UI as "re-enrol suggested." **Never auto-update embeddings** — operator approval required (security risk) |
| H5 | GDPR-style data erasure for ex-employees | Not mentioned | `DELETE /api/persons/{id}` performs multi-step soft-delete: mark `is_active=false`, blank `person_embeddings`, scrub face thumbnails from disk, write `purged_at`. Tracking events retain `global_track_id` (for analytics integrity) but lose `person_id`. Audit log records the deletion |
| H6 | Disk full on JSON spillover buffer | Buffer specced; no quota monitor | Buffer is size-monitored. At 80% full → admin warning. Full → drop oldest + metric `frames_dropped_overflow` |
| H7 | Schema migration under load | Not mentioned | All migrations executed in a maintenance window. Service refuses to start if `alembic current != heads` |
| H8 | Anti-spoofing (printed photo / video replay) | Not mentioned | v1 explicitly **out-of-scope** (documented). Pluggable `LivenessDetector` interface added now to the face pipeline (no-op default). Sets up future MoFA / CDCN integration without architecture change |
| H9 | Camera credentials rotated externally | Not mentioned | Worker logs RTSP auth failure → marks camera state `auth_failed` → distinct admin badge. Distinguished from network outage so operator knows to update credentials |
| H10 | Worker scale-up while running | Not mentioned | Production runbook: add new worker process → it joins the consumer group via `XGROUP CREATECONSUMER`. Existing workers' `XAUTOCLAIM` rebalances naturally. No service restart |
| H11 | Model upgrade rollback | Not mentioned | Each ML model has a version in config + `models/v{N}/` directory layout. Canary procedure: enable new model on 1 camera → observe 24h → global enable. Rollback = config swap + worker restart |
| H12 | Privacy: face images on disk | `thumbnail_path` exists, no encryption note | Thumbnails encrypted at rest with Fernet (Windows: key in DPAPI; Linux: key in `secrets.json` mode 0400). Decryption only when API serves to authorised user |

---

## §I. DB schema delta (consolidated)

All v2 schema changes summarised. Canonical DDL lives in the referenced sections — when migration files are written, copy from there.

| Change | Section with full DDL |
|---|---|
| `cameras` ALTERs (`capability_tier`, `profile_data`, `profiled_at`, CHECK) | §B |
| `CREATE TABLE anomaly_detectors` | §C |
| `zones` ALTERs (`allowed_hours`, `loiter_threshold_s`) | §C |
| `CREATE TABLE maintenance_windows` | §D |
| `alerts` ALTER (`suppressed_by_window_id`) + state value `'suppressed'` | §D |
| `CREATE TABLE alert_dispatches` | §E |
| `CREATE TABLE alert_routing` | §E |
| `CREATE TABLE person_clip_embeddings` | §F.2 |
| `CREATE TABLE audit_log` | §F.3 |

All new tables follow the v1 conventions (BIGINT IDENTITY PK on high-write tables, INT IDENTITY elsewhere, DATETIME2 for timestamps, NVARCHAR for strings, JSON payloads validated against Pydantic schemas before write).

**FAISS index rebuild rule** — both AdaFace and CLIP FAISS indices are rebuilt from their respective MSSQL tables at service startup; MSSQL remains the source of truth. The CLIP index uses a sliding 30-day window matching the forensic search retention.

---

## §J. API delta (consolidated)

```
# §B: camera profiling
POST   /api/cameras/{id}/profile
GET    /api/cameras/{id}/profile
GET    /api/sites/readiness-report.pdf?site=

# §C: anomaly detector management (admin)
GET    /api/anomaly-detectors
PATCH  /api/anomaly-detectors/{id}                 # enable/disable, update config

# §D: maintenance windows
POST   /api/maintenance
GET    /api/maintenance?scope_type=&scope_id=&active=true
PATCH  /api/maintenance/{id}
DELETE /api/maintenance/{id}
GET    /api/maintenance/calendar?from=&to=

# §E: alert routing
GET    /api/alert-routing
POST   /api/alert-routing
PATCH  /api/alert-routing/{id}
DELETE /api/alert-routing/{id}

# §F.2: forensic
GET    /api/forensic/search?q=&from=&to=&zone_id=
GET    /api/forensic/clips/{global_track_id}?around_ts=

# §F.3: audit
GET    /api/audit/verify?from=&to=
GET    /api/audit/export?from=&to=&format=pdf

# §H.3: camera replacement
POST   /api/cameras/{id}/recalibrate-required
```

WebSocket events unchanged from v1 §11.

---

## §K. Updated phase plan

### Phase 1 — Foundation *(unchanged from v1)*
Webcam → Redis Streams → SCRFD/AdaFace/ByteTrack → MSSQL → FastAPI enrolment + health.

### Phase 2 — Identity, anomaly framework, maintenance
- Cross-camera Re-ID (FAISS + zone adjacency)
- Homography + calibration wizard
- **`AnomalyDetector` interface + 6 v1 detectors (UNKNOWN_PERSON, PERSON_LOST, CROWD_DENSITY, INTRUSION, VIOLENCE, LOITERING)**
- **Maintenance window suppression in AlertFSM**
- `reid_matches` audit + correction propagation

### Phase 3 — Hardened pipeline + camera tiering + multi-channel alerts
- **`CameraProfiler` + capability tiering + Site Readiness Report PDF**
- **`AlertDispatcher` + email + Slack + Telegram + webhook**
- **Audit log with hash-chain**
- Hardening items H1, H2, H6, H8, H9, H11, H12

### Phase 4 — Frontend
React: Guard view, Management view, Admin view (incl. maintenance calendar + camera profile UI + audit verify panel). Same scope as v1 §18 plus the new admin panels.

### Phase 5 — Forensic + production hardening
- **Forensic CLIP search** (text-to-clip)
- Prometheus metrics + Grafana
- Load testing at 52-camera scale
- Hardening items H3, H4, H5, H7, H10
- Systemd/NSSM unit files

### Phase 6 — Camera rollout
- Procurement (when customer opts for new cameras) per relaxed v2 spec
- Per-camera homography calibration + capability profiling on real RTSP
- Zone polygon mapping on customer's CAD floor plan
- Security review (auth, RTSP credential encryption, role permissions)

---

## Appendix — sections unchanged from v1

The following v1 sections remain authoritative — no v2 changes:

- v1 §2 Existing Prototype
- v1 §4 Shared Memory Safety
- v1 §5 Backpressure & Frame Dropping
- v1 §6 Inference Pipeline (extended in v2 §C with the gated pool — but face/person/embedder details unchanged)
- v1 §7 Cross-Camera Re-Identification
- v1 §8 Homography
- v1 §10 Database Schema (extended by v2 §I)
- v1 §11 API Design (extended by v2 §J)
- v1 §12 Frontend Design (extended in Phase 4 plan)
- v1 §13 Error Handling & Recovery (extended by v2 §H)
- v1 §14 Degraded Mode
- v1 §15 Event Versioning
- v1 §16 Observability
- v1 §19 Technology Stack Summary

---

**End of v2 design specification.**
