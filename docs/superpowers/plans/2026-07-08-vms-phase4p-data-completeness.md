# Phase 4P — Data Completeness (Backend Endpoints + Frontend Wiring) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: IN PROGRESS — backend tasks (started 2026-07-08; Task 1)**

**Goal:** Kill every hollow widget and dead call found in the 2026-07-08 audit. Implement
the seven backend endpoint groups from spec Part V (persons detail, analytics KPI,
head-count series, system metrics, clip export 202-queued, users CRUD, bookmarks), wire
the six orphaned endpoints from Part VI into the UI, and remove/flag the three 404-ing
frontend calls. Extended 2026-07-08 per the model-stack spec (§9.2, §8.2): person
timeline endpoint (Task 1b — the "where was Brijesh at 2 PM" query), homography
calibration write API + `floor_plans` table (Task 8b), heatmap/floor read APIs (Task 8c),
and calibrator/heatmap frontend wiring (Task 14b). After this phase, nothing on screen is
fake: GPU % is real, uptime is real, KPIs are real, every button does something or
honestly says why it can't.

**Architecture:** Backend: new route files + Pydantic schemas, four new tables
(`camera_status_events`, `export_jobs`, `bookmarks`, `floor_plans`) + one rollup table
(`analytics_head_count_hourly`) + homography calibration columns on `cameras`,
scheduler jobs for metrics sampling and rollups
(scheduler owns all recurring work — invariant §17), Redis for the 5s metrics sample,
WebSocket `system_metrics` event. Frontend: wire existing pages/hooks to the new
endpoints. Data flow honors §0.6: no per-request scans of `tracking_events` — rollups +
indexed aggregates + 60s cache only. Timeline/heatmap queries must be windowed +
index-backed (EXPLAIN recorded in the notes).

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + PostgreSQL (pgvector/pg16 test on 5434),
Redis, pynvml + psutil, pytest; React + TanStack-style hooks + Vitest on the frontend.

**Spec refs:** `2026-07-08-vms-frontend-premium-polish.md` Parts V–VI, §10, §13.1–.2;
`2026-07-08-vms-model-stack-and-analytics-readiness.md` §8.2 (homography APIs) + §9.2
(person timeline — canonical contract for Task 1b);
`2026-05-01-vms-db-edge-cases.md` (constraints for new tables);
`2026-06-12-vms-recording-clips-analytics.md` (export worker lands there, NOT here).

**Depends on:** Backend tasks (1–8c) independent. Frontend wiring (9–15) after 4N.

**Integration tests:** DB-backed tests run against the real PostgreSQL test instance
(`pgvector/pgvector:pg16`, port 5434, container `vms-test-db`) per CLAUDE.md §10 — never a
mocked ORM. Tasks whose tests need larger seeded datasets (timeline coalescing at volume,
heatmap binning) mark those tests `@pytest.mark.integration`; CI runs them on `main` only.

**Backend gate (every task):** `black vms/ tests/ && ruff check vms/ tests/ && mypy vms/ && pytest`
**Frontend gate (tasks 9–15):** `cd frontend && pnpm lint && pnpm typecheck && pnpm test:run`

**Standing rules for every endpoint task:** JWT auth dependency, role gate via the
permissions layer (role AND camera/zone scope where applicable), Pydantic request/response
schemas in `vms/api/schemas.py`, ≥1 positive + ≥1 negative test, no bare numeric literals
(tunables → `config.py` as `VMS_*`), timestamps `datetime.now(timezone.utc).replace(tzinfo=None)`.

---

## Task 1 — `GET /api/persons/{person_id}`

- [x] Failing tests: 200 with full schema (spec §8.1: person_id, full_name, role,
      created_at, embedding_count, last_seen_at, last_seen_camera_id, thumbnail_url|null);
      404 for absent AND for purged person; 403 for role below manager.
      `last_seen_*` from an indexed `tracking_events` lookup (person's latest event —
      verify index exists; add via migration if not).
      → `tests/test_api_persons_detail.py` (8 tests); composite index
      `ix_tracking_events_person_ts` added via migration `d5e6f7a8b9c0` (round-trip tested).
      `role` returns null — persons have no designation column (noted for frontend).
- [x] Implement in `routes/persons.py`. Route order: define BEFORE `/api/persons/search`
      conflicts — FastAPI matches `/search` first only if declared first; add a test
      locking that `/api/persons/search` still resolves (regression guard).
      → detail route declared after `search_persons`; regression test included.
- [x] Verify: gate green. (837 passed, 2026-07-08)

## Task 1b — `GET /api/persons/{person_id}/timeline` (person sightings)

Canonical contract: model-stack spec §9.2. This is the "where was person X at time T"
query — the day-one requirement. No migration needed; reads `tracking_events` via the
`(person_id, event_ts)` index Task 1 guarantees.

- [x] Config first: `VMS_TIMELINE_GAP_S` (default 10) and `VMS_TIMELINE_MAX_SPANS`
      (default 500) in `config.py` — no bare literals in the route.
- [x] Failing tests — coalescing correctness (real test DB, deterministic fixture):
      seed per-frame `tracking_events` for one person across 3 cameras with known gaps;
      assert events on the same `(camera_id, global_track_id)` separated by
      < `VMS_TIMELINE_GAP_S` coalesce into one `{from_ts, to_ts}` visit span, a gap ≥
      threshold splits spans, and a camera change always splits. Exact expected span
      list asserted, ordered by `from_ts` DESC.
- [x] Failing tests — span payload: each span carries `camera_id`, `camera_name`,
      `zone_id`, `zone_name` (nullable), `global_track_id`, `resolved_via`
      (strongest in span: face ≻ body ≻ ble ≻ unknown — test asserts face wins on a
      mixed span), `floor_x`/`floor_y` (latest non-null in span, else null),
      `thumbnail_url|null`.
- [x] Failing tests — filters + limits: default window last-24h; honors `from=`/`to=`;
      optional `camera_id`/`zone_id` filters; 422 when `limit` >
      `VMS_TIMELINE_MAX_SPANS` or `from >= to`.
- [x] Failing tests — authz: role gate manager+; **camera-permission filtering** — a
      manager lacking permission on camera B receives only camera-A spans (rows
      filtered, NOT 403; test with a two-camera fixture and a scoped
      `user_camera_permissions` row).
- [x] Failing tests — GDPR + audit: purged person (embeddings blanked, `person_id`
      SET NULL in `tracking_events`) → 200 with empty list; 404 for a person_id that
      never existed; every request writes `PERSON_TIMELINE_QUERIED` via
      `write_audit_event` (actor, target person_id, window) — assert the audit row
      exists AND the hash chain still verifies.
      → chain assertion done per-row via `compute_row_hash` (full `/api/audit/verify`
      sweep is order-dependent in the shared test DB — tamper tests commit broken rows).
- [x] Implement in `routes/persons.py`: coalescing in SQL — `LAG(event_ts)` window
      function partitioned by `(camera_id, global_track_id)` → gap flag → running
      `SUM` as span id → outer `GROUP BY`. No Python row loops over raw events.
      EXPLAIN recorded in the implementation notes; the plan must show the
      `(person_id, event_ts)` index, never a seq scan of `tracking_events` (§0.6).
      → EXPLAIN ANALYZE at 200k rows/partition: Index Scan, 16.9 ms (see notes).
- [x] `@pytest.mark.integration` volume test: seed ≥50k events for one person on the
      real test DB; endpoint answers a 24h window in < 500 ms and returns ≤
      `VMS_TIMELINE_MAX_SPANS` spans (truncation is explicit: response carries
      `truncated: true`).
- [x] Verify: gate green. (851 passed, 2026-07-09; `tests/test_api_persons_timeline.py`, 14 tests)

## Task 2 — `camera_status_events` + real uptime foundation

- [x] Failing tests (real test DB): model + migration create table
      `(id, camera_id FK ON DELETE CASCADE, status, at)` with CHECK on status enum and
      index `(camera_id, at)`; writer helper `record_camera_status_transition()` inserts
      only on CHANGE (same-status call = no row); migration downgrade round-trips.
      → `tests/test_camera_status_events.py` (6 tests); migration `e6f7a8b9c0d1`.
- [x] Implement model in `vms/db/models.py` + Alembic migration (same commit).
      Helper in `vms/db/camera_status.py`.
- [x] Hook the existing camera-health scheduler job: on observed status change, call the
      helper. Test: simulated flap online→offline→online writes exactly 2 rows.
      → **Deviation:** no camera-health scheduler job exists in the codebase. Hooked the
      two real transition points instead (event-driven, no polling lag):
      `IngestionWorker._mark_camera_inactive()` → 'offline';
      `PATCH /api/cameras/{id}` is_active toggle → 'online'/'offline'.
      Flap test asserts exactly 2 rows after the baseline row.
- [x] Verify: gate green (857 passed, 2026-07-09); round-trip clean on test DB (5434)
      and applied to dev DB (5432).

## Task 3 — `GET /api/analytics/kpi`

- [x] Failing tests: 200 schema per spec §8.2 (head_count_peak, head_count_peak_at,
      avg_dwell_minutes, unknown_person_events, camera_uptime_pct, open_alerts,
      alerts_by_severity); default window last-24h, honors from/to; uptime computed from
      `camera_status_events` over the window (fixture with known transitions → exact pct);
      alerts aggregation via one GROUP BY; 403 below manager; result cached in Redis
      keyed by window with `VMS_ANALYTICS_CACHE_TTL_S` (default 60).
      → `tests/test_analytics_kpi.py` (7 tests incl. redis-down graceful path and
      cache-TTL check).
- [x] Implement `routes/analytics.py` (new router, registered in `api/main.py`).
      head_count_peak from the rollup table (Task 4) with live-window top-up from the
      state snapshot; dwell + unknown-person from indexed aggregate queries — EXPLAIN
      each query in the implementation notes; none may seq-scan `tracking_events`.
      → live top-up via new `get_head_count_aggregator()` in `routes/state.py`.
- [x] Verify: gate green (874 passed, 2026-07-09).

## Task 4 — Head-count rollup + `GET /api/analytics/head-count`

- [x] Failing tests: `analytics_head_count_hourly` model + migration
      `(bucket_start, zone_id NULLable, plant_total, by_zone JSONB or per-zone rows —
      pick per-zone rows: (bucket_start, zone_id, count) with UNIQUE(bucket_start, zone_id))`;
      scheduler rollup job aggregates the past closed hour idempotently
      (`ON CONFLICT DO UPDATE`); backfill helper fills missed hours on startup (bounded
      by `VMS_ROLLUP_BACKFILL_MAX_HOURS`, default 48).
      → per-zone rows with `NULLS NOT DISTINCT` unique (zone_id NULL = plant row);
      migration `f7a8b9c0d1e2`; rollup in `vms/db/analytics_rollup.py`; dedup mirrors
      HeadCountAggregator (person_id for identified, gid for unknown).
- [x] Failing tests: endpoint 200 `{series:[{ts, plant_total, by_zone}]}` for
      `days=7&bucket=hour|day` (day = SUM over hourly), 422 on days>90, 403 below manager.
      → `tests/test_analytics_head_count.py` (10 tests).
- [x] Implement table + migration; scheduler job (scheduler process, not ad-hoc);
      endpoint in `routes/analytics.py`.
      → `head_count_rollup` ScheduledJob, cron `5 * * * *`, backfill-on-each-run.
- [x] Verify: gate green (867 passed, 2026-07-09); migration round-trip clean.

## Task 5 — System metrics: sampler + endpoint + WS event

- [x] Failing tests: sampler job writes JSON to Redis key `system:metrics` with fields
      per spec §8.4 (gpu util/mem via pynvml with graceful `gpu: null` when NVML absent —
      CI has no GPU; cpu_pct/disk via psutil; inference_fps + ingest_lag_ms from existing
      pipeline counters if exposed, else null v1) every `VMS_METRICS_SAMPLE_INTERVAL_S`
      (default 5); endpoint `GET /api/system/metrics` returns the Redis payload (503 with
      `detail="metrics unavailable"` if key absent/stale > 3× interval); any authenticated
      role passes; unauthenticated 401.
      → `tests/test_system_metrics.py` (9 tests); inference_fps/ingest_lag_ms are
      honest nulls in v1 (no cross-process pipeline counters exist yet).
- [x] Implement sampler in the scheduler process; endpoint in new `routes/system.py`.
      → `vms/scheduler/system_metrics.py`; `system_metrics_sample` ScheduledJob with
      cron derived from the setting.
- [x] WebSocket: publish `system_metrics` event on the existing live socket channel each
      sample (reuse the socket broadcast path used by alerts/state; test the event shape).
      → sampler XADDs to `vms:system_metrics`; realtime bridge xreads both streams and
      emits `system_metrics` (scheduler and API are separate processes — the bridge is
      the only socket owner).
- [x] Verify: gate green (883 passed, 2026-07-09; NVML-absent path covered via monkeypatch).

## Task 6 — Clip export: 202-queued (`export_jobs`)

- [ ] Failing tests: `export_jobs` model + migration `(id UUID, requested_by FK users,
      camera_id FK, from_ts, to_ts, reason, state CHECK IN ('QUEUED','RUNNING','COMPLETE',
      'FAILED'), created_at, updated_at)`; `POST /api/forensic/export` validates
      from_ts<to_ts and window ≤ `VMS_EXPORT_MAX_WINDOW_S` (default 300), checks the
      requester's camera permission, writes audit event `CLIP_EXPORT_REQUESTED` via
      `write_audit_event`, returns 202 `{job_id, state:'QUEUED'}`; `GET
      /api/forensic/export/{job_id}` returns state (owner or admin only — 403 otherwise,
      404 unknown); negative: 403 wrong camera scope, 422 bad window.
- [ ] Implement in `routes/forensic.py`. NO worker in this phase (recording spec owns it);
      jobs stay QUEUED honestly.
- [ ] Verify: gate green; migration round-trip clean.

## Task 7 — `/api/users` CRUD

- [ ] Failing tests: GET list (admin only); POST create (username/email uniqueness 409,
      role enum, bcrypt/argon2 hash — reuse existing auth hashing); PATCH role/active/
      camera-permissions; POST `/{id}/reset-password` (returns one-time temp password or
      accepts new password per existing auth design — match `deps.py` conventions);
      DELETE = soft-deactivate (`is_active=false`), never row deletion.
      Guards: self-demotion 409; deactivating/demoting the LAST active admin 409
      (count query under the same transaction); every mutation writes an audit event
      (USER_CREATED / USER_UPDATED / USER_DEACTIVATED / USER_PASSWORD_RESET); non-admin 403.
- [ ] Implement `routes/users.py` + register. Never log/return password hashes (schema
      excludes them; test asserts absence in responses).
- [ ] Verify: gate green.

## Task 8 — `/api/bookmarks`

- [ ] Failing tests: `bookmarks` model + migration `(id, user_id FK CASCADE, camera_id FK
      CASCADE, ts, alert_id NULLable FK SET NULL, note VARCHAR(500), created_at)` index
      `(user_id, camera_id)`; GET (own rows only, optional camera_id filter); POST
      (camera permission check); DELETE own (404-not-403 for others' rows to avoid
      existence leak); guard+ roles.
- [ ] Implement `routes/bookmarks.py` + register.
- [ ] Verify: gate green; migration round-trip clean.

## Task 8b — `floor_plans` table + homography calibration API

Canonical contract: model-stack spec §8.2.1. Backend half of the existing
`HomographyCalibrator.tsx` admin UI. Full floor-plan asset management (upload,
versioning) is deferred to the recording/analytics spec — this task is the minimal
table + calibration write/read.

- [ ] Config first: `VMS_HOMOGRAPHY_MAX_RMS_PX` (default 15) in `config.py`.
- [ ] Failing tests — schema (real test DB): `floor_plans` model + migration
      `(id, name UNIQUE, image_path, scale_m_per_px CHECK > 0, created_at)`;
      `cameras.floor_plan_id` FK nullable ON DELETE SET NULL;
      `cameras.homography_calibration` Text (JSON: `point_pairs`, `rms_error_px`,
      `calibrated_at`, `calibrated_by`) — one migration, downgrade round-trips.
- [ ] Failing tests — `PUT /api/cameras/{id}/homography` (admin only, 403 below):
      body `{point_pairs: [{image:[x,y], floor:[x,y]}] (≥4), floor_plan_id|null}`.
      Server recomputes the matrix with `cv2.findHomography(RANSAC)` — the client
      never supplies the stored matrix. 422 when: < 4 pairs, degenerate/collinear
      pairs (findHomography returns None), or RMS reprojection error >
      `VMS_HOMOGRAPHY_MAX_RMS_PX`. Success: writes `cameras.homography_matrix`
      (row-major 3×3 JSON — same format `project_to_floor()` already reads),
      persists calibration JSON, clears `recalibrate_required_at`, writes audit
      event `CAMERA_CALIBRATED` via `write_audit_event`. Positive test: a known
      synthetic ground-truth homography (generate floor points from image points
      through a fixed matrix) round-trips — recovered matrix projects a held-out
      image point to within 1 floor unit.
- [ ] Failing tests — `GET /api/cameras/{id}/homography` (viewer+ with camera
      permission): returns matrix + calibration metadata + `stale: true` when
      `recalibrate_required_at` is set; 404 when never calibrated.
- [ ] `@pytest.mark.integration` end-to-end: calibrate via the API on the real test
      DB, insert a tracking event through the writer path, assert `floor_x/floor_y`
      populated by `project_to_floor()` with the newly stored matrix.
- [ ] Verify: gate green; migration round-trip clean.

## Task 8c — Floor read APIs: floor plans, heatmap, live floor positions

Canonical contract: model-stack spec §8.2.2. Data sources: `tracking_events.floor_x/
floor_y` (heatmap) and the live state snapshot (positions).

- [ ] Config first: `VMS_HEATMAP_MAX_WINDOW_H` (default 72) and reuse
      `VMS_ANALYTICS_CACHE_TTL_S` from Task 3.
- [ ] Failing tests — `GET /api/floor-plans` (any authenticated role): lists plans
      with camera counts; 401 unauthenticated.
- [ ] Failing tests — `GET /api/analytics/heatmap?floor_plan_id=&from=&to=&bucket_m=`
      (manager+): returns `{bucket_m, cells: [{x, y, count}]}` binned via SQL
      `floor()` division GROUP BY over events whose camera belongs to the plan;
      fixture with hand-placed floor coordinates → exact expected cells; events with
      NULL floor coords excluded; 422 when window > `VMS_HEATMAP_MAX_WINDOW_H` or
      `bucket_m <= 0`; camera-permission filtering (unpermitted cameras' events
      excluded, same doctrine as Task 1b); result Redis-cached keyed by
      (plan, window, bucket).
- [ ] Failing tests — `GET /api/live/floor-positions?floor_plan_id=` (guard+):
      current tracklets from the state snapshot with floor coords + `person_id` +
      `resolved_via`; tracklets from uncalibrated cameras excluded; camera-permission
      filtered.
- [ ] Implement heatmap + positions in `routes/analytics.py`; floor plans in a small
      `routes/floor_plans.py` (or fold into cameras router — pick whichever keeps
      files < 600 lines). EXPLAIN for the heatmap query in the notes — must be
      bounded by the `event_ts` index; no unbounded `tracking_events` scans (§0.6).
- [ ] `@pytest.mark.integration` volume test: 100k events across 2 plans on the real
      test DB; 24h heatmap < 500 ms warm-cache, < 2 s cold.
- [ ] Verify: gate green.

---

## Frontend wiring (after 4N)

## Task 9 — PersonProfilePage + purged-person state

- [ ] Failing tests: page fetches `/api/persons/{id}`; renders profile fields; 404 →
      designed "This person was removed" state (spec §10.6) with back-CTA; loading skeleton.
- [ ] Wire; add "Recent clips" strip fed by `GET /api/forensic/clips/{global_track_id}`
      when the profile exposes a track id (hide the strip when absent).
- [ ] Verify: frontend gate green.

## Task 10 — Analytics dashboard on real data

- [ ] Wire KPI cards to `/api/analytics/kpi` and HeadCountChart to
      `/api/analytics/head-count?days=7` (types from the new schemas); remove any
      client-side uptime computation from `/api/cameras`.
- [ ] Tests: happy path renders real fields; error path already designed in 4O Task 5.
- [ ] Verify: frontend gate green.

## Task 11 — Real system metrics in TopBar + SystemStatusStrip

- [ ] Wire `system_metrics` WS event into `liveStore` (gpuPct, fps, lag); initial fill
      from `GET /api/system/metrics`; `gpu: null` → gauge hidden with tooltip
      "GPU metrics unavailable", never fake 0.
- [ ] Tests: store dispatch on WS event; null-GPU render path.
- [ ] Verify: frontend gate green.

## Task 12 — ClipExportDialog job flow

- [ ] Wire POST → 202 `{job_id}`; success state shows "Export queued" + job id and a
      status check (poll `GET .../export/{job_id}` while dialog open, 5s interval,
      stops on close — no ad-hoc global timers).
- [ ] Tests: queued render; failed-validation (422) shows field errors.
- [ ] Verify: frontend gate green.

## Task 13 — AdminUsersPage CRUD UI

- [ ] Replace "Coming Soon": DataTable of users (name, role, active, last fields
      available), create dialog (RHF+Zod), edit role/active, reset-password with
      confirm, deactivate with typed confirm. Surface 409 guard errors verbatim-friendly
      ("You can't demote the last admin").
- [ ] Element-level `hasPermission` checks; tests per state incl. 409 rendering.
- [ ] Verify: frontend gate green.

## Task 14 — Bookmarks wiring

- [ ] Wire CameraTile FAB Bookmark + unified AlertCard Bookmark to
      `POST /api/bookmarks` (alert bookmark carries alert_id + ts); optimistic toast;
      bookmarks list surfaced where the design system already has a slot (workspace
      panel or TopBar menu — smallest honest placement: a "Bookmarks" section in the
      CommandPalette results + a simple list dialog).
- [ ] Persisted across refresh (fetch on live mount into store).
- [ ] Tests: create/delete flows; permission-hidden for roles without camera access.
- [ ] Verify: frontend gate green.

## Task 14b — Homography calibrator + heatmap + person timeline wiring

- [ ] HomographyCalibrator: wire Save to `PUT /api/cameras/{id}/homography`
      (point pairs from the picker); render returned `rms_error_px`; surface the 422
      reasons verbatim-friendly ("Points are collinear — spread them across the
      floor"); load existing calibration via GET on mount; staleness banner when
      `stale: true` ("Camera was replaced — recalibration required").
- [ ] HeatmapPage: floor-plan selector fed by `GET /api/floor-plans`; heatmap layer
      from `GET /api/analytics/heatmap` (bucket + window controls bounded to the
      backend's 422 limits so the UI can't request an invalid window); empty state
      when the plan has no calibrated cameras ("No calibrated cameras on this floor
      plan" with a link to the calibrator, admin-gated via `hasPermission`).
- [ ] PersonProfilePage (extends Task 9): timeline strip fed by
      `GET /api/persons/{id}/timeline` — visit spans grouped by day, camera/zone
      names, `resolved_via` badge per span (face = solid, body = outline, ble =
      dashed — evidence strength must be visible per spec §9.2), truncation notice
      when `truncated: true`; time-window picker.
- [ ] Tests: calibrator save + 422 render; heatmap empty/loaded states; timeline
      render incl. `resolved_via` badges and empty (purged-person) state.
- [ ] Verify: frontend gate green.

## Task 15 — Orphan wiring + dead-call removal

- [ ] AdminDashboardPage: detector-health card from `GET /api/anomaly-detectors/health`
      (per-detector status pill; degraded → warning styling).
- [ ] MaintenanceCalendarPage: month grid fed by `GET /api/maintenance/calendar?from&to`
      (windows painted on days; recurring expansion comes from the endpoint).
- [ ] AdminCamerasPage header: "Readiness report" download Button →
      `/api/sites/readiness-report.pdf` (admin-gated).
- [ ] CameraDetailPage HardwareTab: "Flag for recalibration" action →
      `POST /api/cameras/{id}/recalibrate-required` with confirm dialog + toast.
- [ ] EnrolmentWizard: verify/fix final step actually POSTs
      `/api/persons/{id}/embeddings` (audit says it never calls); test the wiring.
- [ ] FocusedCamera: delete the HLS URL construction (MJPEG only until recording spec);
      `grep -rn "hls" src/features/live/` → only hls.js lazy-import remnants removed too.
- [ ] CameraTile FAB: Playback button hidden until recording spec (not a dead no-op);
      PTZ stays disabled with the tooltip copy from spec §8.8.
- [ ] Frontend standardizes person search on `/api/persons?q=` (drop `/search` usage).
- [ ] Tests for each wiring; verify: frontend gate green.

## Task 16 — Phase close-out

- [ ] Audit List-1 re-check: `grep -rn "persons/\${\|forensic/export\|hls/index" src/` —
      every call now has a live backend or was removed.
- [ ] Concurrency edge (spec §10.7): double-acknowledge PATCH returns benign
      200/409 — backend test + frontend silent-reconcile test.
- [ ] Both gates green; backend coverage ≥80% on new modules; frontend floors hold.
- [ ] All five migrations round-trip tested (`camera_status_events`,
      `analytics_head_count_hourly`, `export_jobs`, `bookmarks`,
      `floor_plans`+homography columns); `alembic history` linear.
- [ ] Integration suite (`pytest -m integration`) green on the real test DB —
      timeline volume, heatmap volume, homography end-to-end.
- [ ] Update spec §3.2 inventory rows to FIXED; update CLAUDE.md §3; write
      `docs/superpowers/notes/2026-07-08-vms-phase4p-implementation-notes.md`;
      plan Status → COMPLETE.
