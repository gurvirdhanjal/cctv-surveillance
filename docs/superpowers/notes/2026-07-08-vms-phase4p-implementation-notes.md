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
