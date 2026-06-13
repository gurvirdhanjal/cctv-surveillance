# VMS v2 — Hardened Design (Existing-Camera Retrofit + Anomaly Suite + Maintenance + Scaling)

**Design Specification** · 2026-05-01 · **Last updated: 2026-06-13**
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
| Theft / harassment / mobile app / SaaS / shift emails / klaxon / CAD heatmap / tampering detection | — | All explicitly **deferred to v2.x** to keep v1 shippable |
| **PPE compliance (helmet/vest/gloves/mask)** | Not in v1 | **Delivered post-Phase 2d** — `PPEDetector` + `PPEModel` (YOLOv8l SH17 ONNX). See §C detector matrix. |
| **Multi-modal person Re-ID** | ByteTrack + face-only | **Delivered Phase 2d** — YOLOv8x-pose (keypoints) + BoT-SORT + OSNet AIN x1.0 msmt17 (body Re-ID) + BLE badge fallback + `FusionResolver` (Face ≻ Body ≻ BLE) |
| Model lifecycle | Models bundled with code | **Models downloaded on first run** from a manifest (HF Hub or customer mirror, SHA-256 verified). Fine-tunable on customer data via reference recipes. Per-camera version + threshold overrides. CLI: `vms-models download / verify / pin / swap` |
| **GPU acceleration (Phase 6)** | Plain CUDA-EP inference; §G capacity table is the pre-acceleration baseline | **Planned** — `2026-06-13-vms-gpu-acceleration.md` specifies: detector-interval decoupling (§6.0.25), model format normalisation to ONNX (§6.0.5), TensorRT EP FP16 (~2–3× throughput/GPU, §6.1), INT8 detectors (§6.2, arch-gated), NVDEC hardware decode (§6.3), Triton cross-camera dynamic batching (§6.4), multi-GPU sharding (§6.5). DeepStream evaluated last-resort only (§6.6). Target: 52 cameras on one 32 GB GPU at ≤50 ms/frame; second GPU expands to ~100+ cameras. See §G.5 and §K |
| Scheduled jobs | Implicit, scattered | **§M centralises** all 12 production cron jobs under `vms.scheduler` with idempotency, audit logging, and timeout/failure handling |
| Real-time state | Frontend referenced `/api/state/snapshot` and `head_count` WebSocket event with no spec backing | **§N defines** `HeadCountAggregator` component, full snapshot response schema, and adds `head_count`, `alert_state_changed`, `degraded_mode` to the event matrix |

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

-- Shutter type: detected by CameraProfiler, confirmed/overridden by Super Admin.
-- 'unknown' treated conservatively as 'rolling' in InferenceEngine.
ALTER TABLE cameras ADD shutter_type NVARCHAR(10) NOT NULL DEFAULT 'unknown';
ALTER TABLE cameras ADD CONSTRAINT chk_camera_shutter
    CHECK (shutter_type IN ('rolling', 'global', 'unknown'));
```

### API

```
# Camera CRUD (Admin+)
GET    /api/cameras                             # list: id, name, tier, shutter_type, is_active, status
POST   /api/cameras                             # create camera
GET    /api/cameras/{id}                        # full detail
PATCH  /api/cameras/{id}                        # core fields: name, is_active, rtsp_url
PATCH  /api/cameras/{id}/hardware               # shutter_type + tier override (Super Admin only)
PATCH  /api/cameras/{id}/overrides              # model_overrides JSON (Admin+)
GET    /api/cameras/{id}/resolved-config        # full config with source labels — powers Overrides diff view

# Camera profiling (Admin+)
POST   /api/cameras/{id}/profile               # re-runs profiler; detects shutter_type + tier
GET    /api/cameras/{id}/profile               # returns last profile data + tier reason + shutter suggestion
GET    /api/sites/readiness-report.pdf?site=  # generates signed PDF
```

Every `PATCH /hardware` or `PATCH /overrides` request:
1. Writes to `audit_log` (`event_type = CAMERA_HARDWARE_UPDATED` or `CAMERA_OVERRIDES_UPDATED`) with `{actor, camera_id, from, to}`.
2. Publishes `camera_config_changed:{camera_id}` to Redis so `InferenceEngine` hot-reloads that camera's config without a full worker restart.

`GET /api/cameras/{id}/resolved-config` response shape:
```json
{
  "camera_id": 3,
  "settings": {
    "adaface_min_sim": { "value": 0.68, "source": "shutter:rolling" },
    "scrfd_conf":      { "value": 0.45, "source": "shutter:rolling" },
    "burst_frames":    { "value": 5,    "source": "shutter:rolling" },
    "violence_model":  { "value": "movinet_a2", "source": "global_default" },
    "loitering_s":     { "value": 300,  "source": "global_default" }
  }
}
```
`source` values: `"manual_override"` | `"shutter:rolling"` | `"shutter:global"` | `"detector_config"` | `"env_var"` | `"global_default"`.

---

## §C. Anomaly framework *(replaces v1 §9)*

### `AnomalyDetector` interface

```python
class AnomalyDetector(ABC):
    alert_type: str                    # e.g. "VIOLENCE"
    severity: Severity                 # LOW | MEDIUM | HIGH | CRITICAL
    requires_models: tuple[str, ...]   # ("violence",) — gate check
    requires_tier: tuple[str, ...]     # ("FULL", "MID") — tier gate

    def __init__(self, config: dict[str, Any]) -> None: ...

    @abstractmethod
    def should_run(self, ctx: DetectorContext) -> bool:
        """Cheap CPU-side gate. Return False to skip evaluate()."""

    @abstractmethod
    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        """Run rule/model. Return candidate event or None."""

    @abstractmethod
    def fsm_config(self) -> FSMConfig:
        """Sustain duration, cooldown, dedup window."""
```

`DetectorContext` carries `frame: DetectionFrame`, `zone_lookup`, `active_track_zones`, `head_count`, and `violence_score` — everything a detector needs without accessing the DB or Redis directly.

Adding theft / harassment / fall detection in v2.x = one new class + one row in `anomaly_detectors`. **Core architecture never changes.**
PPE compliance is already delivered (see detector matrix below).

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

### Detector matrix (as implemented)

| `alert_type` | Model / mechanism | Trigger gate | Sustained | Cooldown | Severity | Tier required |
|---|---|---|---|---|---|---|
| `UNKNOWN_PERSON` | FAISS identity pipeline | Person tracklet without `person_id` | >500ms in frame | 60s/zone | HIGH | FULL |
| `PERSON_LOST` | Tracker state | `global_track_id` absent everywhere | >30s | 120s | MEDIUM | FULL |
| `CROWD_DENSITY` | YOLO head count + zone | `count > zone.max_capacity` | >10s continuous | 300s/zone | MEDIUM | FULL, MID |
| `INTRUSION` | Zone + schedule rule | Person enters `is_restricted=true` zone outside `zones.allowed_hours` | >2s | 60s/zone | CRITICAL | FULL, MID, LOW |
| `VIOLENCE` | **MoViNet A2 Stream** (TF SavedModel) | YOLOv8x-pose sees ≥2 persons in frame | confidence >0.65 sustained 2s | 30s/zone | CRITICAL | FULL, MID |
| `LOITERING` | Tracker dwell via ZonePresence DB | Single tracklet in zone >`zones.loiter_threshold_s` (default 180s) | continuous | 600s/zone | LOW | FULL, MID |
| `PPE_VIOLATION` | **YOLOv8l SH17** (ONNX, 17-class) — helmet(10), vest(16), gloves(9), mask(5) | Per-tracklet: `ppe_helmet_conf < threshold` OR `ppe_vest_conf < threshold` (gloves/mask opt-in) | >3s continuous | 120s/track | HIGH | FULL, MID |

**Note on VIOLENCE model:** The implementation uses **MoViNet A2 Stream** (not A0 as originally specced). A2 provides streaming-frame inference (~4ms/frame on CPU) via a stateful per-camera context, avoiding the 16-frame clip batch approach. Accuracy: 78.6% Top-1 on Kinetics-400. A0 was the original design choice; A2 was adopted for latency and state management advantages.

### Trigger-gated execution

The `InferenceEngine` separates models into two pools:

- **Always-on pool:** SCRFD (face detection), **YOLOv8x-pose** (person detection + 17 COCO keypoints), **BoT-SORT** tracker. Run on every frame.
- **Gated pool:** AdaFace face embedding (only when keypoint confidence indicates a frontal face — nose + eye conf ≥ `face_kpt_min_conf=0.5`); MoViNet A2 Stream violence (only when ≥2 persons detected); PPEModel (only when configured and persons present); OSNet AIN body Re-ID (per-person crop, only when `VMS_PPE_MODEL` / `VMS_OSNet_MODEL` set).

**Keypoint gate (Phase 2d addition):** YOLOv8x-pose provides 17 COCO keypoints per tracklet. If nose/eye keypoints have low confidence (person facing away, helmet covering face, top-down angle), SCRFD + AdaFace are skipped entirely. This saves ~30% GPU on ceiling cameras where frontal faces are rare.

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
With NVDEC (Phase 6.3, hardware-dependent)       : ~30+ cameras per process
                                                   (decode moves to GPU video engine,
                                                    separate hardware unit from CUDA cores;
                                                    consumer cards have 1–2 NVDEC units —
                                                    a real ceiling at 52 streams;
                                                    data-centre cards are effectively unlimited)
```

Adding cameras adds CPU load linearly. 4 ingestion workers × 13 cams = 52 cams comfortably. Beyond 100 cams: enable NVDEC (Phase 6.3 — requires hardware probe to determine unit count and whether all streams fit) or add ingestion hosts.

**NVDEC is not a free toggle.** It is a Phase 6.3 deliverable gated on `detect_gpu_profile().nvdec_units`. Consumer-grade GPUs may not support all 52 streams in hardware; the excess falls back to software decode. See `2026-06-13-vms-gpu-acceleration.md` §6.3 for the probe-and-fallback design.

#### G.2 GPU inference (the real ceiling)

> **These are plain CUDA-EP baselines** — the floor, not the ceiling. Phase 6 GPU acceleration
> (TensorRT EP FP16 + dynamic batching) targets ≥2× throughput/GPU on the same hardware. See §G.5
> for the post-acceleration model and `2026-06-13-vms-gpu-acceleration.md` for the full design.

```
Total budget = Σ (cameras × fps × model_cost)

Per-camera GPU time @ 15fps with trigger-gated heavy models (plain CUDA-EP baseline):
  SCRFD (face)          : 15 fps × 6 ms    =  90 ms/sec/cam
  AdaFace (embed)       :  5 fps × 4 ms    =  20 ms/sec/cam   (only on detected faces)
  YOLOv8n (person)      : 15 fps × 4 ms    =  60 ms/sec/cam
  CLIP (forensic)       :  2 fps × 5 ms    =  10 ms/sec/cam   (only on detected persons)
  Intrusion rule        : ~0 (CPU-side)
  Violence (gated)      :  5 fps × 25 ms   = 125 ms/sec/cam   (only when ≥2 persons; ~30% of frames in normal ops)
  Loitering (gated)     : negligible (re-uses YOLO + tracker)

Per-camera GPU steady-state ≈ 200-300 ms/sec → ≈ 25-30% utilisation per camera
```

**What Phase 6 changes:** detector-interval decoupling (§6.0.25) cuts the primary-detector passes
by the interval factor; TensorRT FP16 (§6.1) delivers 2–3× inference throughput; dynamic batching
(§6.4) amortizes kernel-launch overhead across cameras. Actual numbers will be measured against this
baseline by the §6.0 benchmark harness on the real deployment GPU before any claim is made.

#### G.3 GPU SKU capacity at 1080p / 15fps (CUDA-EP baseline)

| GPU | VRAM | Camera capacity (CUDA-EP) | Camera capacity (Phase 6 TRT+batching, estimated) | Indicative cost (₹) |
|---|---|---|---|---|
| RTX 4060 / A2000 | 8 GB | 10 – 15 | 20 – 30† | ~80k |
| RTX 4090 / A4000 | 16 GB | 30 – 40 | 60 – 80† | ~2.5L |
| **32 GB GPU (deployment target)** | **32 GB** | **50 – 65** | **100 – 130†** | ~3–5L |
| RTX 6000 Ada / L40S | 48 GB | 80 – 100 | 160 – 200† | ~6L |
| A100 / H100 | 40–80 GB | 150+ | 300+† | ~10L+ |

† TensorRT FP16 + Triton dynamic batching estimates. **These are hypotheses, not guarantees** — the
§6.0 benchmark harness will measure them against the actual deployment GPU before any claim ships.

**Important: VRAM is not the bottleneck** for this model stack (SCRFD + AdaFace + YOLOv8x-pose +
OSNet + MoViNet + PPE + CLIP ≈ 6–9 GB resident). The binding constraint is CUDA compute throughput.
A 32 GB card's compute tier determines camera capacity — the surplus VRAM enables aggressive batching
and a second model replica per GPU.

The 52-camera plant fits a **32 GB GPU** comfortably at the CUDA-EP baseline, with substantial
headroom when Phase 6 acceleration is applied. The second available 32 GB GPU (§G.5) then
expands capacity to ~100–130 cameras before any infrastructure change is needed.

#### G.4 DB writes — negligible at v1 scale

52 cams × 15 fps × ~3 detections/frame = ~2,300 rows/sec → well within PostgreSQL's batched-write capacity (500ms/100-row flush already specced).

### Scaling runbook — "add 50 more cameras"

1. **Up to ~80 cameras (single GPU + Phase 6 acceleration)**
   - Add ingestion worker processes; partition cameras across workers via `cameras.worker_group`.
   - Apply Phase 6 GPU acceleration (§G.5): TensorRT FP16 + Triton dynamic batching alone pushes
     the 32 GB GPU to ~100–130 cameras (estimated). Detector-interval decoupling (§6.0.25) is the
     cheapest first lever.
   - No infrastructure change.

2. **80 → 150 cameras (two GPUs, one host)**
   - Add the second available 32 GB GPU to the same server (Phase 6.5).
   - Shard cameras across GPUs via `cameras.worker_group` (already used for ingestion partitioning —
     no new concept introduced).
   - Each GPU runs its own TensorRT engines / Triton instance consuming its camera partition from
     `frames:groupN` Redis Streams.
   - `IdentityService` stays single (not GPU-bound) — receives detections from both GPUs.
   - `DBWriter` scales per GPU partition.
   - This is the two-node topology from step 3, **collapsed onto one host with two cards** — lower
     infrastructure cost, higher GPU–GPU bandwidth via PCIe, clean failover (one GPU's cameras
     degrade, the other's are unaffected).
   - Documented as the **"dual-GPU single-host"** deploy in the production runbook.

3. **150 → 400 cameras (two separate GPU hosts)**
   - Stand up a second GPU host (same spec as the first).
   - Move Redis to its own machine (shared message bus between hosts).
   - Each host runs its own `InferenceEngine` + Triton, consuming a partition of `frames:groupX`.
   - `IdentityService` stays single, receives detections from all hosts.
   - `DBWriter` scales out trivially per partition.
   - Documented as the **"two-node deploy"** in the production runbook.

4. **400+ cameras (multi-tenant or multi-site)**
   - Swap Redis Streams for **Kafka** — same consumer-group API shape, no logic rewrite.
   - Shard `IdentityService` by zone-cluster.
   - Multi-site: each site is a self-contained deployment that ships only alerts + tracking summaries
     to a central management instance.

### G.5 GPU acceleration roadmap (Phase 6)

> **Full design:** `docs/superpowers/specs/2026-06-13-vms-gpu-acceleration.md`
>
> **Status:** Draft spec approved. No implementation until Phase 5 priorities are weighed and each
> sub-phase has its own plan file (`docs/superpowers/plans/`).

The §G.2 capacity table is a plain CUDA-EP baseline. Phase 6 climbs a ladder of independently
shippable sub-phases, stopping as soon as the 52-camera / ≤50 ms/frame target is met:

| Sub-phase | What it does | Expected effect | Needs TensorRT? |
|---|---|---|---|
| §6.0 — Harness | GPU hardware probe (`detect_gpu_profile()`) + benchmark framework | Establishes the actual baseline on the real card | No |
| §6.0.25 — Detector interval | YOLO runs every Nth frame; tracker coasts between runs | Cuts primary-detector GPU-time by ~1/N; cascade stages (face/body embedding) are **exempt** and stay gate-based | No |
| §6.0.5 — ONNX normalisation | Export all models to ONNX (`.pt` → Ultralytics export, `.pth` → `torch.onnx.export`, TF SavedModel → `tf2onnx`); validate numerically | Prerequisite for §6.1+; MoViNet may stay on native TF runtime | No |
| §6.1 — TensorRT FP16 | Add `TensorrtExecutionProvider` to ONNX Runtime provider list in `detector.py`, `embedder.py`, `ppe.py`; warm-up pass on startup | **2–3× inference throughput/GPU** — the single biggest win | Yes |
| §6.2 — INT8 detectors | Post-training quantisation on YOLO/SCRFD; **embedding models stay FP16** | +30–50% on detector stages (arch-gated: Turing+ only) | Yes |
| §6.3 — NVDEC | Move RTSP decode from CPU to GPU video engine (hardware-probe gated) | Frees CPU cores; removes §G.1 decode ceiling | No |
| §6.4 — Triton batching | `InferenceEngine` becomes a Triton client; frames from all cameras batched into single GPU pass | Largest multiplier at high camera counts | Yes |
| §6.5 — Multi-GPU | Shard cameras across both 32 GB GPUs via `cameras.worker_group`; each GPU its own Triton instance | ~2× aggregate capacity; redundancy | Yes |
| §6.6 — DeepStream | **Go/no-go only** — spike if §6.1–6.5 still fall short | Potential further gain; CUDA lock-in + pipeline rewrite cost | N/A |

**Identity correctness is non-negotiable across all sub-phases.** FP16/INT8 changes embedding
numerics. Before any precision change ships on AdaFace or OSNet, the §6.0 harness must confirm
cosine-similarity drift vs FP32 stays within threshold — and any threshold adjustment requires
`/advisor` sign-off per CLAUDE.md §0.5. INT8 is applied to detectors first; embedders require
explicit evaluation and approval.

**The Redis-Streams bus and FAISS-as-derived-cache invariants (CLAUDE.md §17) are preserved
throughout.** Triton (§6.4) changes only what happens inside `InferenceEngine`'s model-execution
call — ingestion → inference still flows through `frames:groupN`; PostgreSQL remains the source
of truth; FAISS is rebuilt from `person_embeddings` at startup.

### Why doubling cameras doesn't double Redis load

The shared-memory frame transport is the architecture's "secret weapon." Redis carries only 24-byte frame pointers; raw pixels never traverse the bus. Adding cameras adds ingestion CPU but not message-bus bandwidth. Phase 6.4 (Triton batching) exploits this further: the GPU processes one large batch from N cameras in the same kernel launch that previously processed one frame from one camera.

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
| H11 | Model upgrade rollback | Not mentioned | Each ML model has a version in config + `models/v{N}/` directory layout. Canary procedure: enable new model on 1 camera → observe 24h → global enable. Rollback = config swap + worker restart. Full model lifecycle (download / fine-tune / per-camera override) covered in §L |
| H12 | Privacy: face images on disk | `thumbnail_path` exists, no encryption note | Thumbnails encrypted at rest with Fernet (Windows: key in DPAPI; Linux: key in `secrets.json` mode 0400). Decryption only when API serves to authorised user |

---

## §I. DB schema delta (consolidated)

All v2 schema changes summarised. Canonical DDL lives in the referenced sections — when migration files are written, copy from there.

| Change | Section with full DDL |
|---|---|
| `cameras` ALTERs (`capability_tier`, `profile_data`, `profiled_at`, CHECK) | §B |
| `cameras` ALTER (`shutter_type`, CHECK `chk_camera_shutter`) | §B, §L.3.1 |
| `cameras` ALTER (`model_overrides`) | §L.3 |
| `CREATE TABLE anomaly_detectors` | §C |
| `zones` ALTERs (`allowed_hours`, `loiter_threshold_s`) | §C |
| `CREATE TABLE maintenance_windows` | §D |
| `alerts` ALTER (`suppressed_by_window_id`) + state value `'suppressed'` | §D |
| `CREATE TABLE alert_dispatches` | §E |
| `CREATE TABLE alert_routing` | §E |
| `CREATE TABLE person_clip_embeddings` | §F.2 |
| `CREATE TABLE audit_log` | §F.3 |

All new tables follow the v2 conventions (BIGSERIAL PK on high-write tables, SERIAL elsewhere, TIMESTAMPTZ for timestamps, TEXT/VARCHAR for strings, JSON payloads validated against Pydantic schemas before write).

**FAISS index rebuild rule** — both AdaFace and CLIP FAISS indices are rebuilt from their respective PostgreSQL tables at service startup; PostgreSQL remains the source of truth. The CLIP index uses a sliding 30-day window matching the forensic search retention.

---

## §J. API delta (consolidated)

```
# §B: camera CRUD + hardware config
GET    /api/cameras
POST   /api/cameras
GET    /api/cameras/{id}
PATCH  /api/cameras/{id}
PATCH  /api/cameras/{id}/hardware              # Super Admin only
PATCH  /api/cameras/{id}/overrides             # Admin+
GET    /api/cameras/{id}/resolved-config       # Admin+

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
Webcam → Redis Streams → SCRFD/AdaFace/ByteTrack → PostgreSQL → FastAPI enrolment + health.

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

### Field Deployment *(operational, runs in parallel with Phase 3–5 — not a software phase)*
- Procurement (when customer opts for new cameras) per relaxed v2 spec
- Per-camera homography calibration + capability profiling on real RTSP
- Zone polygon mapping on customer's CAD floor plan
- Security review (auth, RTSP credential encryption, role permissions)

### Phase 6 — GPU Acceleration *(spec approved; plan not yet written)*
> Full design: `docs/superpowers/specs/2026-06-13-vms-gpu-acceleration.md`
>
> This phase begins after Phase 5 priorities are confirmed by the user. Each sub-phase gets its
> own plan file before code. Recommended entry sequence: §6.0 → §6.0.25 → §6.0.5 → §6.1.

- **§6.0** — GPU hardware probe (`detect_gpu_profile()`) + benchmark harness; record CUDA-EP
  baseline on the actual deployment card.
- **§6.0.25** — Detector-interval decoupling: YOLO every Nth frame, tracker coasts. Cascade
  stages (SCRFD→AdaFace, YOLO→OSNet) are **exempt** — they stay gate-based. Cheapest win,
  requires no TensorRT.
- **§6.0.5** — Model format normalisation to ONNX: `.pt` (Ultralytics export), `.pth`
  (`torch.onnx.export`), TF SavedModel (`tf2onnx`). Every export validated numerically.
  MoViNet may stay on native TF if stateful ONNX export is impractical — decision recorded.
- **§6.1** — ONNX Runtime TensorRT EP, FP16. Provider list change in `detector.py`,
  `embedder.py`, `ppe.py` + engine cache + startup warm-up. Identity-accuracy guard mandatory
  before shipping. Target: ≥2× frames/sec/GPU.
- **§6.2** — INT8 quantisation on detectors (Turing+ arch only). Embedding models (AdaFace,
  OSNet) stay FP16. INT8-on-embedders requires `/advisor` sign-off.
- **§6.3** — NVDEC hardware decode, hardware-probe gated. Consumer-card NVDEC unit limit
  handled by probe-and-fallback; no silent truncation.
- **§6.4** — Triton Inference Server: cross-camera dynamic batching. `InferenceEngine` becomes
  Triton client; Redis-Streams bus and FAISS invariants preserved.
- **§6.5** — Multi-GPU sharding: both 32 GB GPUs active, cameras sharded via
  `cameras.worker_group`. `IdentityService` stays single.
- **§6.6** — DeepStream go/no-go: only evaluated if §6.1–6.5 cannot reach the ≤50 ms/frame
  target. Decision record required; not a rewrite by default.

**Hard target:** sustained 52 cameras at ≤50 ms/frame end-to-end on a single 32 GB GPU (CLAUDE.md
§0.6). The second GPU provides headroom to ~100–130 cameras and redundancy — it is not required
for the base 52-camera deployment.

---

## §L. Model lifecycle — download, fine-tune, configure *(NEW)*

The codebase ships *without* model binaries. Models are downloaded from a declared manifest on first run, with SHA-256 verification. Fine-tuned variants are first-class — operators can produce, upload, canary-test, and swap them per camera.

### L.1 Models are not bundled — they are downloaded

Repo carries `models/manifest.json` declaring every required model + version + source + checksum:

```json
{
  "schema_version": "1",
  "default_source_kind": "huggingface",        // 'huggingface' | 'https' | 'local'
  "default_mirror": "https://models.apltechno.com/vms/v1/",  // air-gapped customer mirror
  "models": {
    "scrfd_2.5g": {
      "version": "1.0.0",
      "source": "huggingface://repo-name/scrfd_2.5g.onnx",
      "sha256": "<digest>",
      "size_bytes": 12345678,
      "purpose": "face_detection",
      "input_shape": [1, 3, 640, 640],
      "fine_tunable": false
    },
    "adaface_ir50": {
      "version": "1.0.0",
      "source": "huggingface://repo-name/adaface_ir50.onnx",
      "sha256": "<digest>",
      "purpose": "face_embedding",
      "fine_tunable": true,
      "training_recipe": "scripts/finetune/adaface.md"
    },
    "yolov8n_person":      { "fine_tunable": true,  "training_recipe": "scripts/finetune/yolov8.md" },
    "movinet_a0_violence": { "fine_tunable": true,  "training_recipe": "scripts/finetune/violence.md" },
    "clip_vit_b32":        { "fine_tunable": false }
  }
}
```

CLI (`vms-models` console-script entry-point):

```
vms-models download                 # fetch all + verify SHA-256, exits non-zero on mismatch
vms-models verify                   # re-verify checksums on disk
vms-models list                     # show installed versions and active per-camera overrides
vms-models pin <name> <version>     # lock a specific version (writes to manifest.lock)
vms-models swap <name> <path.onnx>  # register a fine-tuned ONNX (signs + copies to models/v{N}/)
```

Service refuses to start if any required model fails verification.

### L.2 Fine-tuning workflow

For models marked `fine_tunable: true`:

1. **Dataset export** — `vms-models export-dataset --model adaface --since 2026-01-01 --out customer_faces.tar`
   - Pulls high-quality face crops from `person_embeddings` + raw frames within retention window.
   - Includes labels from `persons` (employee_id, person_type).
   - Optional flag `--include-unknowns` packs recurring unknown tracklets as candidate negatives.

2. **Train (offline)** — operator (or APL Techno's services team) runs the reference recipe:
   - `scripts/finetune/adaface.py` — fine-tunes the AdaFace head on customer's employee distribution.
   - `scripts/finetune/yolov8.py` — fine-tunes person detector for customer-specific clothing (uniforms, PPE) using Ultralytics CLI.
   - `scripts/finetune/violence.py` — fine-tunes MoViNet on customer-flagged false positives + true positives.
   - Each recipe is a documented Markdown + Python pair; the recipe is the contract, not the code.

3. **Export to ONNX with embedded metadata** (via `onnx.helper.set_model_props`):

   | Key | Purpose |
   |---|---|
   | `vms.base_model` | Which stock model this was fine-tuned from |
   | `vms.base_version` | Stock model version |
   | `vms.trained_at` | ISO-8601 timestamp |
   | `vms.customer_id` | Tenant identifier |
   | `vms.dataset_size` | Number of training samples |
   | `vms.eval_metrics` | JSON: precision, recall, F1 on held-out test set |

4. **Upload + canary** — `POST /api/models/upload` (multipart):
   - Server verifies HMAC signature against deployment secret.
   - Reads embedded metadata; rejects if `vms.base_model` doesn't match the slot the operator is uploading into.
   - Stores in `models/v{N}/` with new version string; records audit log entry.
   - Operator runs canary: assigns the new model to **one camera** via per-camera override, observes ≥24h, then promotes to global default if eval is good.

### L.3 Per-camera model + threshold overrides

Customers may want different models per camera (fine-tuned face model in HR area, stock model elsewhere; stricter thresholds at the gate, looser inside). Add a single JSON column for both model + threshold overrides:

```sql
ALTER TABLE cameras ADD model_overrides NVARCHAR(MAX) NULL;
-- JSON example:
--   {
--     "models":     { "face_embedder": "adaface_ir50_acme_v2", "violence": null },
--     "thresholds": { "adaface_min_sim": 0.78, "scrfd_conf": 0.55 }
--   }
-- model name = use that specific version from models/ directory
-- null      = inherit system default for that slot
-- absent    = inherit system default
```

`InferenceEngine` resolves overrides at camera-config-load time and routes that camera's frames to the appropriate model instance. Models are loaded once and shared across cameras that use them — no per-camera GPU memory blowup.

Manual overrides in `model_overrides` always win over shutter-type adjustments (§L.3.1) — an operator can restore a rolling-shutter camera to global thresholds if they know the specific camera handles motion well.

### L.3.1 ShutterProfile — pipeline adjustments by shutter type

`cameras.shutter_type` is detected by `CameraProfiler` (motion-skew analysis on a 30-frame clip) and confirmed/overridden by a Super Admin via `PATCH /api/cameras/{id}/hardware`. `unknown` is treated conservatively as `rolling`.

**Threshold adjustments applied when `shutter_type = 'rolling'`:**

| Setting | Global default | Rolling adjustment | Reason |
|---|---|---|---|
| `adaface_min_sim` | 0.78 | **0.68** | Face geometry distortion lowers embedding fidelity |
| `scrfd_conf` | 0.55 | **0.45** | Skewed bounding boxes reduce detector confidence |
| `burst_frames` | 1 | **5** | Pick highest-SCRFD-confidence frame from 5 consecutive frames (InferenceEngine config, not a DB column) |
| FusionResolver body weight | 1.0× | **1.2×** | Body Re-ID (OSNet) is distortion-tolerant; upweight it |

When `shutter_type = 'global'`: all settings use global defaults; single-frame face ID is reliable.

**Detection heuristic** (CameraProfiler): captures 30 frames with a subject walking laterally at ~1.5 m/s; measures horizontal skew variance of SCRFD bounding boxes across frames. Skew variance > 0.04 → suggest `rolling` (confidence = 1 − variance/0.10, clamped to 60–95%). Operator sees the suggestion with confidence score and clicks Confirm or overrides in the Hardware tab.

### L.4 Configuration storage hierarchy

```
1. Per-camera manual override    (cameras.model_overrides — models + thresholds)
2. Shutter-type adjustment       (cameras.shutter_type → ShutterProfile, see §L.3.1)
3. Per-detector global config    (anomaly_detectors.config_json + .model_version)
4. Global env vars / settings    (VMS_ADAFACE_MIN_SIM, VMS_SCRFD_CONF, ...)
5. Hard-coded defaults           (vms/config.py)
```

First match wins. `GET /api/cameras/{id}/resolved-config` (§B API) shows the **resolved value + which level it came from** for every setting — operators always see what the system is actually using. "Reset to defaults" button on every override.

### L.5 Versioning, rollback, audit

- `models/v{N}/` directory layout (already in §H11) keeps prior versions.
- Rollback = update `anomaly_detectors.model_version` (global) or `cameras.model_overrides` (per-camera), restart the affected inference worker.
- Every model swap, threshold change, or per-camera override mutation is recorded in the `audit_log` (§F.3) with `{actor, camera_id, from_version, to_version, reason}`.
- Routine: weekly cron emits a report of all active model versions across cameras, surfacing drift between intended and actual configuration.

### L.6 Phase placement (updates §K)

- **Phase 3** adds: `models/manifest.json` + `vms-models download/verify/list/pin` CLI + per-camera override columns + threshold-override admin UI.
- **Phase 5** adds: fine-tuning recipes (`scripts/finetune/*`) + dataset export tool + `POST /api/models/upload` + canary flow + signed-model verification.

---

## §M. Scheduled jobs and cron orchestrator *(NEW — closes gap surfaced 2026-05-01)*

The system has multiple background jobs running on schedules. These were specified piecemeal across the v2 spec, edge-cases spec, and §L; this section lists them in one place so deployment automation can register them all.

### Cron orchestrator

A single Python process `vms.scheduler` runs in production (systemd unit `vms-scheduler.service`, Windows: `vms-scheduler` NSSM service). It reads `vms/scheduler/jobs.py` declaratively:

```python
@dataclass(frozen=True)
class ScheduledJob:
    name: str
    cron: str                                # standard 5-field cron
    handler: Callable[[], None]              # idempotent
    timeout_s: int                           # kill if it runs longer
    on_failure: Literal["log", "alert"]
    audit_event_type: str                    # written to audit_log on each run
```

All jobs are idempotent: a missed run can be safely re-executed. Every successful or failed execution writes an `audit_log` row.

### Job registry (v1 in scope)

| Job | Cadence | Purpose | Spec ref |
|---|---|---|---|
| `partition_create_next_month` | 25th of each month, 02:00 | Create next month's `tracking_events` partition before rollover | edge-cases §4 |
| `archive_old_partitions` | Daily 03:00 | Switch out partitions > 12 months → Parquet on object storage → drop | edge-cases §4 |
| `index_optimize` | Daily 04:00 | Ola Hallengren `IndexOptimize` proc — reorganise > 10%, online rebuild > 30% | edge-cases §12 |
| `update_statistics` | Daily 04:30 | After index work, refresh stats on hot tables | edge-cases §12 |
| `audit_chain_verify` | Daily 05:00 | Walk full `audit_log` chain; fire CRITICAL on broken link | edge-cases §14 |
| `faiss_drift_check` | Daily 05:30 | Compare DB embedding count vs FAISS vector count; rebuild if drift > 5 | edge-cases §15 |
| `model_version_report` | Weekly Monday 06:00 | Report active model versions per camera; flag drift between intended + actual | §L.5 |
| `alert_dispatch_dead_letter_drain` | Hourly | Retry failed dispatches in `dead_letter_dispatches`; drop after age > 24h with admin alert | §E |
| `worker_heartbeat_check` | Every 10s | Verify each worker's `heartbeat:{worker_id}` Redis key; admin-alert on >2 consecutive misses | v1 §16 |
| `maintenance_calendar_refresh` | Every 30s | Reload active windows into `MaintenanceCalendar` in-memory cache | §D |
| `clip_retention_purge` | Daily 02:30 | Delete `person_clip_embeddings` rows older than 30 days; drop snapshot files | §F.2 |
| `dr_drill_reminder` | Quarterly | Open a ticket reminding ops to run the disaster-recovery drill | edge-cases §9 |

### Failure handling

- A job that exceeds `timeout_s` is killed; admin alert emitted.
- A job whose handler raises is logged; `on_failure='alert'` jobs also trigger an admin webhook.
- The scheduler itself emits a heartbeat to Redis `scheduler:heartbeat`; if absent for >2× the shortest cron, monitoring fires CRITICAL.

### Phase placement

`vms.scheduler` ships in **Phase 3** alongside the dispatcher and audit log. Earlier phases run jobs manually; the scheduler is what "production-ises" them.

---

## §N. Real-time state aggregator and snapshot API *(NEW — closes gap surfaced 2026-05-01)*

### N.1 HeadCountAggregator

A new component in the **Identity Service** process. Subscribes to `tracking` Redis Stream events and maintains an in-memory map `{zone_id: set[global_track_id]}` updated on every event.

Outputs:

| Output | Where | Cadence |
|---|---|---|
| `head_count` Socket.io event | WebSocket fanout | every 1s |
| `head_count_zone_<id>` Redis Stream entry | Audit and analytics | every 1s |
| HTTP response field on `/api/state/snapshot` | API | on demand |

Pseudo-implementation:

```python
class HeadCountAggregator:
    def __init__(self) -> None:
        self._by_zone: dict[int, set[str]] = defaultdict(set)
        self._last_seen: dict[str, tuple[int, datetime]] = {}  # gtid -> (zone, ts)

    def on_tracking_event(self, ev: TrackingEvent) -> None:
        if ev.zone_id is None:
            return
        prev = self._last_seen.get(ev.global_track_id)
        if prev is not None and prev[0] != ev.zone_id:
            self._by_zone[prev[0]].discard(ev.global_track_id)
        self._by_zone[ev.zone_id].add(ev.global_track_id)
        self._last_seen[ev.global_track_id] = (ev.zone_id, ev.event_ts)

    def evict_stale(self, now: datetime, ttl_s: int = 30) -> None:
        """Remove tracks that haven't been seen for ttl_s; called every second."""
        cutoff = now - timedelta(seconds=ttl_s)
        for gtid, (zid, ts) in list(self._last_seen.items()):
            if ts < cutoff:
                self._by_zone[zid].discard(gtid)
                del self._last_seen[gtid]

    def snapshot(self) -> HeadCountSnapshot:
        total = sum(len(s) for s in self._by_zone.values())
        return HeadCountSnapshot(
            plant_total=total,
            by_zone={zid: len(tracks) for zid, tracks in self._by_zone.items()},
            ts=datetime.utcnow(),
        )
```

Eviction runs every second; the aggregator emits its snapshot at the same cadence.

### N.2 Updated WebSocket event matrix (extends v1 §11)

| Event | Direction | Payload | Throttling |
|---|---|---|---|
| `head_count` | server → client | `{plant_total, by_zone: {[zone_id]: count}, ts, schema_version}` | every 1s |
| `alert_state_changed` | server → client | `{alert_id, new_state, actor_user_id, ts, schema_version}` | immediate |
| `degraded_mode` | server → client | `{enabled: bool, reason: str, ts, schema_version}` | immediate |
| `subscribe_camera` | client → server | `{camera_id}` | ad-hoc |
| `unsubscribe_camera` | client → server | `{camera_id}` | ad-hoc |
| `subscribe_track` | client → server | `{global_track_id}` | follow mode |

(These are additions; `person_location`, `alert_fired`, `track_corrected`, `camera_snapshot`, `worker_health` from v1 §11 remain as specified.)

### N.3 `/api/state/snapshot` — response schema

Used by the frontend on initial load and after WebSocket reconnect to rehydrate the entire live state. Must complete in <500ms p95.

```json
{
  "ts": "2026-05-01T14:32:11.123Z",
  "schema_version": "1",
  "head_count": {
    "plant_total": 23,
    "by_zone": { "1": 5, "2": 0, "3": 12, "4": 6 }
  },
  "active_tracks": [
    {
      "global_track_id": "8f42...",
      "person_id": 7,
      "camera_id": 4,
      "zone_id": 3,
      "bbox": [120, 200, 220, 480],
      "floor_x": 12.5,
      "floor_y": 8.3,
      "ts": "2026-05-01T14:32:10.987Z"
    }
  ],
  "active_alerts": [
    {
      "alert_id": 12345,
      "alert_type": "VIOLENCE",
      "severity": "CRITICAL",
      "state": "active",
      "camera_id": 7,
      "zone_id": 3,
      "global_track_id": "...",
      "triggered_at": "2026-05-01T14:31:55.000Z",
      "snapshot_url": "/api/alerts/12345/snapshot.jpg"
    }
  ],
  "cameras": [
    {
      "camera_id": 1, "name": "Loading Bay 1", "status": "online",
      "capability_tier": "FULL", "in_maintenance": false
    }
  ],
  "workers": [
    { "worker_id": "ingest-A", "status": "healthy", "cam_count": 13, "ts": "..." }
  ],
  "degraded": null
}
```

When the system is in degraded mode, `degraded` is non-null:

```json
"degraded": { "redis": "unreachable", "since": "2026-05-01T14:30:00Z" }
```

### N.4 Implementation note

`HeadCountAggregator` lives in **Phase 2** (alongside the alert FSM); the `/api/state/snapshot` endpoint ships in **Phase 1B** initially with a stub head_count, upgraded to real values in Phase 2.

---

## §O. Multi-Modal Person Tracking (Phase 2c/2d — delivered)

This section documents design decisions made and implemented after the original v2 spec was written.

### §O.1 Tracker upgrade

| Component | Original spec | Implemented |
|---|---|---|
| Person detector | YOLOv8n | **YOLOv8x-pose** (person + 17 COCO keypoints) |
| Tracker | ByteTrack | **BoT-SORT** (camera motion compensation via sparse optical flow) |
| Config | `bytetrack_custom.yaml` | `botsort_custom.yaml` |

### §O.2 Body Re-ID (OSNet)

Cross-camera re-identification now uses body appearance as the **primary** signal and face as secondary. This is the correct priority for factory ceiling cameras where frontal faces are rarely visible.

| Model | OSNet AIN x1.0 msmt17 |
|---|---|
| Output | 512-dim L2-normalised body embedding |
| Training data | MSMT17 (15 diverse datasets, 1,041 identities) |
| Rank-1 accuracy | 73% on DukeMTMC-reID (8 cameras, calibrated 2026-06-01) |
| Thresholds | `reid_body_confirmed_sim=0.51` (95% recall), `reid_body_cross_cam_sim=0.56` |

### §O.3 FusionResolver — multi-modal identity

Once a person is identified (at entry gate via face, or via BLE badge), their `person_id` propagates to all cameras tracking the same `global_track_id` via body Re-ID.

Priority order: **Face (FAISS) ≻ Body gallery anchor ≻ BLE badge**

`assign_and_identify()` returns `(global_track_id, person_id, resolved_via)` where `resolved_via` is one of `'face' | 'body' | 'ble' | 'unknown'`. This is written to `tracking_events.resolved_via` for audit.

### §O.4 BLE badge fallback

When camera-based Re-ID fails (person in a dead zone, occluded, or too small), a Bluetooth Low Energy badge reader confirms zone-level presence. MQTT-based reader → Redis stream → `BleConsumer` → `anchor_person_by_badge()` in IdentityEngine.

Config: `VMS_BLE_MQTT_BROKER`, `VMS_BLE_ZONE_READER_MAP_JSON`. Empty broker = BLE disabled (default).

### §O.5 PPE Compliance (delivered, not deferred)

See §C detector matrix (`PPE_VIOLATION` row). The implementation uses YOLOv8l trained on SH17 (17 classes). Factory-relevant classes: helmet(10), vest(16), gloves(9), mask(5) — verified from model.names. Gloves and mask checking is **opt-in** via `check_gloves=True` / `check_mask=True` in the detector config row.

---

## §P. Future Development — Post-Phase 5 *(NOT scheduled — record for next design cycle)*

This section captures known limitations identified during Phase 2d/3 implementation that are out of scope for Phase 5 but must not be forgotten. Each item has a concrete trigger condition that should prompt a design session before implementation.

---

### §P.1 Appearance Drift — Returning Person After Long Absence

**Problem.** A person who was last seen weeks or months ago may have changed appearance significantly (weight loss/gain, haircut, facial hair, ageing). The current gallery system stores embeddings as an unweighted buffer (N=8 most recent per tracklet, Phase 2c). After a long gap the buffer holds only stale embeddings, and cosine similarity at re-entry may fall below the `adaface_min_sim` threshold even though the person is genuinely the same individual.

**Observed failure modes:**

| Weight change | Entry gate (face-forward cam) | Floor cam (ceiling, body only) | Outcome |
|---|---|---|---|
| ≤10 kg | cos_sim drops ~0.02–0.04, typically still ≥ 0.72 | Body sim borderline | Correctly identified |
| 10–20 kg | cos_sim drops ~0.05–0.10, may fall to 0.65–0.71 | Body sim likely below 0.51 | UNKNOWN_PERSON alert fires incorrectly |
| >20 kg | cos_sim < 0.65 | Body sim fails | New identity record created — duplicate person |

The same degradation applies to:
- Ageing (slower drift, same mechanism)
- Significant haircut (frontal hairline changes AdaFace input region)
- New glasses or beard (partial occlusion changes embedding)

**Two mechanisms to implement:**

**P.1.1 — Soft-match + operator confirmation queue**

When cosine similarity is in the range `[adaface_soft_min_sim, adaface_min_sim)` (suggested: 0.62–0.72), rather than firing `UNKNOWN_PERSON` immediately:

1. Compute top-3 candidate matches from FAISS ranked by similarity.
2. Create a `soft_match_candidate` alert (new alert type, LOW severity, no notification — UI only).
3. Alert payload: `{person_id, similarity, camera_id, thumbnail_url, timestamp}` for each candidate.
4. Guard dashboard shows a "Pending Confirmation" queue. Operator clicks "Yes, same person" or "No, new person."
5. On confirmation: merge galleries, update `person_embeddings` with the new embedding, clear the alert.
6. On rejection: promote to full `UNKNOWN_PERSON`, create new person record.

Config additions:
```
VMS_ADAFACE_SOFT_MIN_SIM=0.62   # lower bound of soft-match zone (below = hard unknown)
```

**P.1.2 — Gallery freshness monitoring + re-enrollment nudge**

Flag person records whose most recent embedding is older than a configurable threshold:

1. Nightly cron job queries `person_embeddings` for records with `created_at < now() - VMS_GALLERY_STALE_DAYS` (suggested default: 60 days).
2. Creates a `GALLERY_STALE` maintenance alert per person (INFO severity, suppressed from guard view).
3. Next time the person appears at an entry gate with a frontal-quality face (SCRFD confidence ≥ 0.85, face area ≥ 12000 px²): automatically enrol the new embedding alongside existing ones. Log `event_type='GALLERY_REFRESHED'` to audit_log.
4. Management dashboard shows a "Gallery age" column on the Persons list with colour coding (green < 30d, amber 30–90d, red > 90d).

Config additions:
```
VMS_GALLERY_STALE_DAYS=60       # days before gallery considered stale
VMS_AUTO_REFRESH_GALLERY=true   # enable auto-enrol on high-quality re-sighting
VMS_AUTO_REFRESH_SCRFD_MIN=0.85 # minimum face confidence for auto-refresh
```

**Implementation notes for the design session:**
- Soft-match threshold must be per-camera-tier: FULL tier can use 0.62, MID/LOW tier should use 0.65 (lower quality embeddings from these cameras have higher noise floors).
- Gallery refresh must write through `vms.identity.faiss_dirty.publish_enrol()` — same path as manual enrolment.
- GDPR: a refreshed embedding is new biometric data. The auto-refresh audit entry must record the trigger condition so a GDPR audit can confirm it was the same person who consented at initial enrolment.

**Spec refs when designing:** §C (anomaly framework, new alert type), §D (maintenance windows — suppress nudges during downtime), §G.7 (audit_log constraints), GDPR purge rules in §F.3.

---

### §P.2 Body Re-ID Threshold Re-Calibration After Appearance Change

**Problem.** The `reid_body_confirmed_sim=0.51` threshold was calibrated from simulation on DukeMTMC (Phase 2d). This dataset does not model large intra-person appearance changes across time. After significant weight loss, body embeddings from the same person can drop to cosine similarity ~0.40–0.48 — below the current threshold.

**Proposed fix (design session required):**
- After a successful face re-identification (sim ≥ adaface_min_sim), capture the body embedding for that sighting.
- If the body sim against the existing body gallery is below 0.51 but face confirmed ≥ 0.72: **accept the body match as "face-assisted confirmed"** and add the new body embedding to the gallery.
- Effectively: face identity acts as a trusted label to update the body gallery, re-anchoring it to the new appearance.
- Do NOT lower the global `reid_body_confirmed_sim` threshold — that increases false-positive body matches across all cameras.

---

*End of §P. These items are NOT in any active phase plan. They require a design session and a new spec section before implementation.*

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
