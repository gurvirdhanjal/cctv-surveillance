# VMS Video Recording, Alert Clips & Time-Series Analytics
**Design Specification** · 2026-06-12
**Status:** Draft

This spec captures three hardening capabilities identified in a competitive review against
enterprise VMS (Genetec Security Center, Milestone XProtect, Avigilon/Verkada, BriefCam, Frigate).
It is a **design document only** — no implementation is scheduled by this file. When greenlit, it
becomes one or more phased plans in `docs/superpowers/plans/` (CLAUDE.md §16). Target phase: **3**,
alongside the alert dispatcher.

The three capabilities:

1. **Video recording + alert clip playback** — the highest-value gap. Today, when a `VIOLENCE`
   or `INTRUSION` alert fires, a guard gets no footage to review. We add a recording tier and an
   alert-clip endpoint so the guard watches the ~30 seconds around the event.
2. **Continuous recording + live/forensic playback** — per-camera recorded video the operator can
   scrub, plus in-browser live view.
3. **Time-series analytics** — historical occupancy/dwell dashboards ("average occupancy by hour
   over 6 months"), built on PostgreSQL rollups with no new service.

---

## 0. Current state (what exists today)

| Area | Today |
|---|---|
| Frames | RTSP → `cv2.VideoCapture` → resize → SHM ring (1 frame, `vms/ingestion/shm.py`) → **discarded** after inference. No disk persistence, no recording, no ffmpeg/HLS anywhere. |
| Storage | `vms/storage/backends.py` `StorageBackend` Protocol (`write/read/delete/exists/url`), local + MinIO. `write_snapshot()`/`write_thumbnail()` in `vms/storage/media.py` exist but are unused. `generate_key()` produces date-partitioned keys. |
| Alerts | `Alert` model (`vms/db/models.py`) has **no media column**. Chain `Alert.triggered_at` + `camera_id` (+ `global_track_id`) locates the moment. Dispatcher (`vms/dispatcher/`) is text-only. |
| Anomaly | `AnomalyEvent` (payload dict) → `AlertFSM` (sustain/dedup) → persists `Alert` row + publishes to the `alerts` Redis stream. `FIRED` is the hook point for clip availability. |
| Analytics | Head count is in-memory only (`HeadCountAggregator`, 30 s TTL, exposed via `GET /api/state/snapshot`). `zone_presence(entered_at, exited_at)` logs raw intervals. **No rollups, no aggregation endpoints.** |
| DB | PostgreSQL 16 + pgvector, **bare metal** (no docker-compose in repo). `tracking_events` partitioned monthly (`vms/db/partition_manager.py`). No TimescaleDB. |
| Scheduler | Invariant (CLAUDE.md §17): the scheduler owns all cron jobs. Retention prune + analytics rollups go there — no ad-hoc timers. |

---

## Part 1: Recording Tier

### 1.1 Pluggable `RecordingBackend` Protocol

Recording is fronted by a Protocol, the same seam pattern used for `StorageBackend` and
`AnomalyDetector`. The cost is a thin interface; the payoff is that a customer who already owns an
NVR (Milestone, Genetec, a Hikvision DVR) becomes an *adapter* rather than a rip-and-replace. The
concrete v1 implementation is FFmpeg.

```python
from datetime import datetime
from pathlib import Path
from typing import Protocol


class RecordingBackend(Protocol):
    def start_camera(self, camera_id: int, rtsp_url: str) -> None: ...
    def stop_camera(self, camera_id: int) -> None: ...
    def get_clip(self, camera_id: int, start_ts: datetime, end_ts: datetime) -> Path: ...
    def health(self) -> dict[int, str]: ...  # camera_id -> "recording" | "error" | "stopped"
```

### 1.2 `FFmpegRecordingBackend` — concrete implementation

One FFmpeg process per camera, **separate from the OpenCV decode path** — it does *not* reuse the
decoded SHM frames (that would waste CPU re-encoding). It connects to the same RTSP source and
remuxes the camera's already-encoded H.264 directly to disk with `-c copy`: no decode, no
re-encode, **no GPU**. CPU cost is negligible — it is moving packets from the network to disk.

```
camera RTSP ──┬── OpenCV decode → SHM → InferenceEngine   (existing; ≤50 ms/frame, untouched)
              └── FFmpeg remux  → HLS .ts segments         (new recording tier)
```

Per-camera command:

```
ffmpeg \
  -rtsp_transport tcp \
  -i rtsp://<user>:<pass>@<host>/<stream> \
  -c copy \
  -f hls \
  -hls_time 10 \
  -hls_list_size 0 \
  -hls_flags append_list+delete_segments \
  -hls_segment_filename "recordings/camera_{id}/%Y-%m-%dT%H/seg_%03d.ts" \
  -strftime 1 \
  recordings/camera_{id}/index.m3u8
```

`-c copy` is the critical flag — pure remux, no GPU touch.

### 1.3 Storage layout — HLS `.ts` segments, no DB index

```
recordings/
  camera_1/
    2026-06-12T14/
      seg_000.ts
      seg_001.ts
      seg_002.ts
    index.m3u8
  camera_2/
    ...
```

HLS with 10-second `.ts` segments is the right format because:

- **Seeking** to "30 s before the alert" = find the segments whose strftime path covers the time
  range. Trivial; no database.
- **Retention cleanup** = a file mtime sweep (`find recordings -name '*.ts' -mtime +N -delete`),
  no DB rows to reconcile.
- **Playback** = native HLS in `hls.js` / `video.js` in the browser, no transcode server.

There is intentionally **no `recording_segments` table** — the filesystem layout plus the per-hour
`index.m3u8` manifests are the index. PostgreSQL remains the source of truth for everything else;
recorded video is a self-describing on-disk artifact addressed by `(camera_id, timestamp)`.

### 1.4 Lifecycle wiring

Recording starts when a camera is registered/activated and stops on deactivation. This hooks the
same `camera_config_changed` Redis event the `InferenceEngine` already subscribes to — no new
control plane. The RecordingBackend's `health()` feeds the camera status surfaced in the Admin UI.

Security: the RTSP URL (which carries credentials) is **never logged**, at any level
(CLAUDE.md §7.2). Log `camera_id` only.

### 1.5 Retention — per-camera, scheduler-owned

Add a per-camera retention column:

```
ALTER TABLE cameras ADD COLUMN recording_retention_days INT NOT NULL DEFAULT 7;
```

Some cameras (e.g. a perimeter or cash room) may need 30 days; others 7. Purge runs as a scheduler
job — **never** an ad-hoc `threading.Timer` or fire-and-forget task (CLAUDE.md §17):

```python
ScheduledJob(
    name="recording_retention_purge",
    cron="0 3 * * *",                       # daily 03:00
    handler=purge_old_segments,
    timeout_s=300,
    on_failure="alert",
    audit_event_type="RECORDING_PURGE_COMPLETE",
)
```

Implementation note for whoever builds this: with `-hls_list_size 0` the playlist keeps every
segment, so `-hls_flags delete_segments` does **not** prune on its own. The daily mtime sweep is
the real retention mechanism; `delete_segments` only matters if `hls_list_size` is later bounded.

### 1.6 Capacity (sizing + sales number)

1080p H.264, typical low-motion factory scene: ~500 kbps average per camera.

```
52 cameras × 500 kbps × 86,400 s/day ≈ 280 GB/day
  7-day retention  ≈ 2.0 TB
 30-day retention  ≈ 8.4 TB
```

A single 10 TB NAS drive comfortably covers 52 cameras at 7-day retention. This is the number for
deployment sizing and sales conversations. Bitrate is camera/scene dependent — high-motion or
higher-resolution streams scale this up linearly; the per-camera retention column lets the operator
trade storage against history per camera.

---

## Part 2: Alert Clips, Live View & Forensic Playback

### 2.1 Clip extraction

`get_clip(camera_id, start_ts, end_ts)` locates the `.ts` segments covering `[T − pre, T + post]`
from the strftime layout, then concatenates and trims them with FFmpeg `-c copy` (fast — trimming
at segment boundaries is effectively instantaneous) into a temporary MP4 served by the API.

```python
def get_clip(self, camera_id: int, start_ts: datetime, end_ts: datetime) -> Path:
    # 1. enumerate the seg_*.ts files whose hour-paths intersect [start_ts, end_ts]
    # 2. ffmpeg concat + -ss/-t trim, -c copy, to a temp MP4
    # 3. return the path; the API streams it for GET /api/alerts/{id}/clip
    ...
```

The alert-FIRED path already persists the `Alert` row and publishes to the `alerts` stream; that is
where clip availability is wired in. **Open decision for the implementation plan:** extract the clip
lazily on first view, or eagerly at FIRED.

- *Lazy* keeps storage lean (most alerts are never reviewed) and naturally satisfies the post-buffer
  (by the time a guard clicks, `T + post` has elapsed). Risk: the covering segments must still be
  within the rolling retention window when the guard looks — fine for review within
  `recording_retention_days`, but a clip a guard wants months later would be gone.
- *Eager* extraction at FIRED copies the window to durable storage so it outlives segment retention,
  at the cost of work for clips nobody watches.

Recommended default: **lazy**, with an optional "pin/export" action that copies a clip to durable
`StorageBackend` (`clips/` prefix) when an operator wants to keep it. The plan should confirm.

### 2.2 API additions

Every endpoint is behind authentication **and** a `user_camera_permissions` check — even a
`manager` cannot pull footage from a camera outside their permission set (CLAUDE.md §7.1).

```
GET /api/alerts/{id}/clip                        # triggers get_clip(), streams the MP4
GET /api/cameras/{id}/live                        # returns the HLS manifest URL for live view
GET /api/forensic/playback?camera_id=&from=&to=   # manual clip extraction / scrub
```

The live-view endpoint — in-browser HLS with zero plugin dependency — is what turns the guard UI
from a wall of snapshots into something operators actually use. Media serving must support HTTP
**Range (206)** responses so the player can seek within a clip or recording.

### 2.3 Frontend

The frontend design spec (`docs/superpowers/specs/2026-05-01-vms-frontend-design.md`) currently
shows no media in the AlertCard. This spec calls for two additions there (to be detailed in the
frontend spec when implementation is greenlit):

- an `hls.js`/`video.js` player in the AlertCard / Focused view for the alert clip and live stream;
- a forensic scrub player with a time selector in the Management view, backed by
  `GET /api/forensic/playback`.

a11y and performance budgets follow the existing frontend spec.

---

## Part 3: Time-Series Analytics

### 3.1 Approach — PostgreSQL rollup tables (no new service)

Historical analytics are served from **PostgreSQL rollup tables** populated by a scheduler job — no
TimescaleDB, no InfluxDB, no Docker, no new query language. Rationale:

- InfluxDB is a separate stateful daemon (new service to run, secure, back up; Flux/InfluxQL) — the
  worst fit for a single-server on-prem deployment that already runs PostgreSQL.
- TimescaleDB is a PostgreSQL extension (installable bare-metal, not strictly Docker), but adds an
  extension dependency some locked-down customer servers resist, and `CREATE INDEX CONCURRENTLY` is
  unsupported on hypertables.
- Plain rollup tables get ~90% of the value with **zero** new dependencies.

The rollup schema is kept compatible with a later TimescaleDB **continuous aggregate** so a Tier-3
(1000+ camera) deployment can upgrade in place — consistent with the Tier-3 note in
`2026-05-28-vms-storage-scalability.md`.

### 3.2 Rollup tables

```
occupancy_rollup_hourly(zone_id, bucket_ts, avg_count, max_count, coverage_s)
dwell_rollup_daily(zone_id, day, p50_dwell_s, p95_dwell_s, visit_count)
```

A scheduler hourly job aggregates `zone_presence` enter/exit intervals into
`occupancy_rollup_hourly` (integrating overlapping intervals per hour bucket), upserting idempotently
on `(zone_id, bucket_ts)`. `dwell_rollup_daily` derives from completed presence intervals.

### 3.3 Query-trap guardrails

Per the project's `pg-timescale-query-traps` guidance, every analytics query must be bounded:

- Use `DISTINCT ON` / `LATERAL` + `LIMIT`; **never** an unbounded `.all()` over months of rows.
- Index `zone_presence(entered_at)` so the rollup job range-scans rather than seq-scans.
- The read API serves from the small rollup tables, never from raw `zone_presence`/`tracking_events`
  over long ranges.
- Any startup-time DDL must gate `ALTER`/`ADD COLUMN` behind an `information_schema` existence check
  (our migrations run via Alembic in a maintenance window, so standard DDL is acceptable there).

### 3.4 API

```
GET /api/analytics/occupancy?zone=&from=&to=&granularity=hour   # reads occupancy_rollup_hourly
GET /api/analytics/dwell?zone=&from=&to=                         # reads dwell_rollup_daily
```

Authenticated + permission-checked. Frontend Management view renders the charts.

---

## 4. Cross-cutting: GDPR & security

- **Recorded video is biometric/personal data.** Deletion is **retention-based** (the per-camera
  `recording_retention_days` sweep), not person-based: video is indexed by `(camera_id, time)`, so a
  GDPR person-purge (`DELETE /api/persons/{id}`) does not and cannot selectively erase that person
  from recorded footage. This distinction must be documented in the deploy runbook and the privacy
  notice. Footage ages out on the retention schedule.
- **At-rest encryption** of recorded video is deferred to the Phase 5 cipher; until then the
  `recordings/` volume must be on an encrypted disk (document in the deploy runbook), consistent with
  the existing face-thumbnail handling (CLAUDE.md §7.2).
- **Every playback/live/forensic endpoint** is behind auth + `user_camera_permissions`
  (CLAUDE.md §7.1). RTSP URLs are never logged (§7.2).

---

## 5. Architectural-invariant compliance (CLAUDE.md §17)

| Invariant | How this design complies |
|---|---|
| PostgreSQL is source of truth | Rollups + camera config live in PG. Recorded video is a self-describing on-disk artifact addressed by `(camera_id, time)` — not a competing source of truth. |
| Redis Streams are the inter-service bus | Lifecycle hooks the existing `camera_config_changed` event; the alert path uses the existing `alerts` stream. |
| Scheduler owns all cron jobs | Retention purge and analytics rollups are `ScheduledJob`s — no ad-hoc timers. |
| Thresholds/sizes live in config | Segment length, retention default, clip pre/post, bitrate assumptions all in `get_settings()`. |
| Inference path untouched (≤50 ms/frame) | The recorder is a separate `-c copy` FFmpeg process — no decode, no GPU, no per-frame DB/Redis work added to inference. |

---

## 6. Deferred (out of scope for this spec)

Documented here so scope is unambiguous; none are designed in this file:

- **Model upgrades** — VideoMAE-V2 (violence), CLIP ViT-L/14 or SigLIP (forensic), TransReID (body
  Re-ID), YOLOv9/RT-DETR (detection). Low architectural risk: handled via `models/manifest.json`
  swap + re-calibration, not a pipeline change.
- **Multi-site** — central pane-of-glass; likely a NATS JetStream migration from Redis Streams for
  geo-distributed deployments.
- **ONVIF Profile S/T/G depth** — PTZ control from the UI, relay outputs, and camera-side event
  subscriptions (motion, tampering); bidirectional access-control integration (badge swipe ↔ camera
  pop-up). The system is currently receive-only.
- **MLOps** — a `model_metrics` table tracking precision/recall estimates from operator
  acknowledge-vs-dismiss feedback, feeding fine-tuning decisions.

---

## 7. When implementation is greenlit

This spec becomes phased plan(s) in `docs/superpowers/plans/` (CLAUDE.md §16), targeted at Phase 3
alongside the dispatcher. Suggested phase decomposition: recording tier (Part 1) → alert clip + live
+ forensic API and frontend (Part 2) → time-series analytics (Part 3). The alert-clip endpoint is the
single feature that closes the "interesting demo → tool guards actually use" gap and should lead.
