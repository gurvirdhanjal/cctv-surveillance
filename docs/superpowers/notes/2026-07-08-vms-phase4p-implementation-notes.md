# Phase 4P — Data Completeness — Implementation Notes

Companion to `docs/superpowers/plans/2026-07-08-vms-phase4p-data-completeness.md`.
The plan says what to do; this file records what actually happened and why.

---

## Task 1 — `GET /api/persons/{person_id}` (2026-07-08, commit `172863ea`)

- Response follows spec §8.1 exactly. **`role` returns `null`** — the `persons` table
  has no designation/role column. Adding one is a product decision + migration not in
  this plan; the frontend should render null as "—". If a real designation field is
  wanted, it needs a plan checkbox first.
- `full_name` maps to `Person.name` (the DB column was never renamed).
- Purged persons 404 (`is_active=False`); the timeline endpoint intentionally differs
  (200 empty) per spec §9.2.
- Route declared **after** `/persons/search` in the file — FastAPI matches in
  declaration order, and `/persons/{person_id}` would otherwise capture "search" and
  422 on the int parse. A regression test locks this.
- New composite index `ix_tracking_events_person_ts (person_id, event_ts)` via
  migration `d5e6f7a8b9c0` (round-trip tested). Serves the last-seen
  `ORDER BY event_ts DESC LIMIT 1` without a sort node, and the Task 1b timeline
  window. The old single-column `ix_tracking_events_person_id` was **kept** (dropping
  an index on the populated partitioned table is a separate decision; additive change
  only).

## Task 1b — `GET /api/persons/{person_id}/timeline` (2026-07-09)

- Coalescing done entirely in SQL (`_TIMELINE_SQL` in `routes/persons.py`):
  `LAG(event_ts)` per `(camera_id, global_track_id)` → gap flag at
  `VMS_TIMELINE_GAP_S` (default 10 s) → running `SUM` numbers spans → `GROUP BY`.
  Latest non-null zone/floor values win within a span via
  `(array_agg(x ORDER BY event_ts DESC) FILTER (WHERE x IS NOT NULL))[1]`.
  Strongest `resolved_via` wins via `MIN(CASE ... face=1, body=2, ble=3, else 4)`.
- **EXPLAIN ANALYZE evidence (§0.6):** 200k rows in the current-month partition
  (10k target person + 190k noise), ANALYZE'd:
  `Index Scan using tracking_events_y2026m07_person_id_idx ... Index Cond: (person_id = N)`,
  Execution Time **16.9 ms**. No seq scan. (At 100%-selectivity synthetic data the
  planner correctly prefers a seq scan — 79.7 ms — which is why the fixture includes
  noise rows.) The planner picks the single-column person index for full-window reads;
  the composite `person_ts` index serves the last-seen lookup and narrow windows.
- Volume test: 50k events, each its own span → 500 spans returned,
  `truncated: true`, query answered well under the 500 ms budget (runs in the default
  suite; `integration` marker is not excluded by addopts).
- **Camera-permission semantics established** (first route to enforce
  `user_camera_permissions`): admin unrestricted; non-admin with permission rows →
  filtered to those cameras (rows filtered, not 403); non-admin with **zero** rows →
  unrestricted, because current deployments don't populate the table. Locked by
  `test_timeline_manager_without_permission_rows_sees_all`.
- **Purged persons return 200 + empty spans** (spec §9.2). Note: the GDPR purge does
  NOT null `person_id` in `tracking_events` (the FK is `ON DELETE SET NULL`, but purge
  never deletes the person row) — the endpoint therefore refuses to query events for
  inactive persons explicitly, rather than relying on the FK behaviour the spec
  assumed. Raw rows still exist in the DB; whether purge should also null
  `tracking_events.person_id` is an open GDPR question worth a spec follow-up.
- Every 200 response writes a `PERSON_TIMELINE_QUERIED` audit event (surveillance
  lookup). Test verifies the row's hash via `compute_row_hash` directly — a full
  `/api/audit/verify` sweep is order-dependent in the shared test DB because the audit
  tamper tests commit deliberately broken rows.
- `global_track_id` is cast to text in SQL (`::text`) — raw `text()` queries bypass
  SQLAlchemy's per-column UUID adaptation.
- Thumbnails: best-effort `DISTINCT ON (global_track_id)` lookup into
  `person_clip_embeddings` for the returned spans only (≤ limit rows).

## Task 2 — `camera_status_events` + transition writer (2026-07-09)

- **Plan deviation:** the plan (and spec §8.2) said "written by the existing health
  scheduler job" — no such job exists. Camera status changes at exactly two places
  today, and both now call `record_camera_status_transition()`:
  `IngestionWorker._mark_camera_inactive()` (RTSP failure threshold → 'offline') and
  `PATCH /api/cameras/{id}` (manual is_active toggle → 'online'/'offline').
  Event-driven beats a polling job: transitions are recorded at the moment they
  happen with no sampling lag. If a periodic health prober lands later (ONVIF probe,
  Phase 6 rollout), it calls the same helper.
- Helper semantics: first-ever call writes a **baseline row**; same-status calls write
  nothing; caller owns the commit. Uptime math (Task 3) treats "no events in window"
  as online-for-the-whole-window.
- Camera creation writes no baseline row — Task 3 must handle cameras with zero
  status history.

## Task 4 — head-count rollup + series endpoint (2026-07-09)

- Chose per-zone rows over JSONB (plan's stated preference). The plant-total row is
  `zone_id NULL`; the UNIQUE constraint uses **`NULLS NOT DISTINCT`** (PG15+) so the
  plant row upserts through the same `ON CONFLICT ON CONSTRAINT` path as zone rows.
- **Head-count semantics:** an hourly bucket counts DISTINCT heads seen during the
  hour, deduped exactly like the live `HeadCountAggregator` (§N.1): identified
  persons by `person_id` across tracks, unknowns by `global_track_id`
  (`COALESCE('p'||person_id, 'g'||gid)` SQL key). This is "unique visitors per
  hour", not instantaneous peak — instantaneous peak would need sub-hour sampling.
- The rollup always writes the plant row (even 0) — its presence marks the hour as
  processed, which is what backfill resumes from. Zone rows only for zones seen.
- `bucket=day` **sums** hourly uniques per the plan. Note this over-counts a person
  present in multiple hours (footfall-style number, not daily uniques) — accepted as
  planned; revisit if the dashboard needs daily uniques.
- Scheduler job `head_count_rollup` (cron `5 * * * *`) just calls
  `backfill_missed_hours()` — one code path for the steady state, missed hours, and
  cold start alike, bounded by `VMS_ROLLUP_BACKFILL_MAX_HOURS=48`.

## Task 3 — analytics KPI endpoint (2026-07-09)

- `head_count_peak` = MAX over Task 4's hourly plant rows in the window, topped up by
  the live in-process `HeadCountAggregator` (raw `snapshot()`, not EMA-smoothed) when
  the window includes "now" — the open hour has no rollup row yet. New getter
  `get_head_count_aggregator()` in `routes/state.py`.
- `avg_dwell_minutes` = AVG of per-`global_track_id` (max−min event_ts) spans in the
  window. Window query is bounded by the `event_ts` index; the aggregate runs on the
  matched rows only. Same index posture as the timeline EXPLAIN (Task 1b notes).
- `camera_uptime_pct`: per-camera offline-seconds reconstructed from
  `camera_status_events` (status at window start = latest event ≤ start, default
  online; no history = 100%), averaged over all cameras, rounded to 2 dp.
- Redis cache keyed `analytics:kpi:{from}:{to}`, TTL `VMS_ANALYTICS_CACHE_TTL_S=60`;
  Redis down → compute uncached with a WARNING (tested via monkeypatch).
- **Test flake found + fixed:** an hour-aligned test window made the Redis cache key
  identical across runs within the TTL — the second run got the first run's cached
  body. Test windows now carry a sub-hour offset. Rule of thumb: any test hitting a
  cached endpoint must use a per-run-unique window.
- mypy gotcha: `Row.count` resolves to the tuple `count()` method — label aggregate
  columns (`.label("peak_count")`) instead of exposing a column literally named
  `count` through raw Row attribute access.

## Task 5 — system metrics (2026-07-09)

- The scheduler and API are separate processes, so the sampler cannot `sio.emit`
  directly. Each sample lands twice in Redis: the `system:metrics` string (read by
  `GET /api/system/metrics`, 503 when absent or older than 3× the interval) and an
  XADD to `vms:system_metrics` (maxlen 100). `run_bridge` now xreads BOTH streams
  (alerts + metrics) in one call and emits `system_metrics` to the socket.
- `inference_fps` and `ingest_lag_ms` ship as **null** — no cross-process pipeline
  counters exist yet. When the inference engine exports counters (Prometheus metrics
  exist — a Redis mirror would be the v2 source), fill them in; never fake 0.
- GPU block is `null` on any NVML failure (import, init, no device) — frontend Task 11
  hides the gauge on null.
- mypy: pynvml/psutil have no stubs → `# type: ignore[import-untyped]` per the
  croniter precedent. redis-py's `xread` dict param is invariant — the cursor dict is
  annotated with redis-py's exact key/value union.

## Task 6 — clip export 202-queued (2026-07-09)

- Jobs are created QUEUED and stay QUEUED — the FFmpeg export worker belongs to the
  recording spec (`2026-06-12-vms-recording-clips-analytics.md`), not this phase.
  The `updated_at` + state CHECK are ready for that worker.
- `requested_by` FK requires a real users row; a JWT whose subject has no users row
  gets 403 "Requesting user not found" (deleted-user edge; mirrors the purge route's
  actor handling).
- **Frontend contract mismatch found:** `ClipExportDialog.tsx` posts
  `{camera_id, start, end, format, label}` but the backend (per the plan/spec) takes
  `{camera_id, from_ts, to_ts, reason}`. Task 12 must rewire the dialog; recorded on
  the Task 6 checkbox so it can't be silently skipped.

## Environment notes

- A Docker engine restart mid-session killed `vms-test-db`, `vms-redis`, and
  `vms-postgres` (all Exited 255). Symptom: 11 suite failures, most with Redis
  connection errors. Restarting the containers fixed all but the audit-chain test
  (real bug in the test's global-verify assumption, fixed as above).
- `alembic` CLI reads `.env` → dev DB on **5432**; pytest pins the test DB on
  **5434**. Migration round-trips must be tested against both when run manually:
  `VMS_DB_URL=postgresql://vms:vms@localhost:5434/vms_test alembic upgrade head`.
- The conftest **downgrades to base after every pytest session** — the test DB has no
  schema between runs; ad-hoc psql/EXPLAIN sessions must `alembic upgrade head` first.
