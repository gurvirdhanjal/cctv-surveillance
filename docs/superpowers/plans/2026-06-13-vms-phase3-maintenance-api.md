# Maintenance Window API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: NOT STARTED**

**Goal:** Complete the Maintenance Window REST API. The route file
`vms/api/routes/maintenance.py` currently exposes only `GET /api/maintenance`
(list active windows). Spec §D requires five endpoints. This plan adds the four
missing ones: `POST`, `PATCH`, `DELETE`, and `GET /api/maintenance/calendar`.

**Architecture:** FastAPI routes → SQLAlchemy ORM (`MaintenanceWindow`) →
PostgreSQL. Writes append to `audit_log` via `write_audit_event()` and publish a
Redis cache-invalidation event consumed (eventually) by the orchestrator's
`MaintenanceCalendar`. No schema migration — the table and all CHECK constraints
already exist.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, croniter (already a dependency,
used by `MaintenanceCalendar`), pytest + httpx ASGITransport.

**Spec refs:** `2026-05-01-vms-v2-hardened-design.md` §D (Maintenance windows —
DB schema, suppression logic, API surface). DB constraints:
`vms/db/models.py` `MaintenanceWindow` (`chk_mw_scope`, `chk_mw_sched`,
`chk_mw_one_time`, `chk_mw_recurring`, `chk_mw_window_positive`).

---

## Context the implementer must know before starting

### The model (already migrated — do NOT add a migration)

`MaintenanceWindow` (vms/db/models.py:153) fields:

| Field | Type | Notes |
|---|---|---|
| `window_id` | int PK | autoincrement |
| `name` | str(200) | NOT NULL |
| `scope_type` | str(20) | `'CAMERA'` \| `'ZONE'` (chk_mw_scope) |
| `scope_id` | int | FK target depends on scope_type; not a DB FK |
| `schedule_type` | str(20) | `'ONE_TIME'` \| `'RECURRING'` (chk_mw_sched) |
| `starts_at` | datetime \| None | ONE_TIME only |
| `ends_at` | datetime \| None | ONE_TIME only |
| `cron_expr` | str(100) \| None | RECURRING only |
| `duration_minutes` | int \| None | RECURRING only |
| `suppress_alert_types` | Text \| None | NULL = suppress ALL; else JSON array string |
| `is_active` | bool | default True |
| `reason` | str(500) \| None | audit trail |
| `created_by` | int | **NOT NULL** FK users.user_id (ondelete NO ACTION) |
| `created_at` | datetime | default `_utcnow_naive` |

DB CHECK constraints the API validation must mirror (so we return 422, not a
500 from a constraint violation):

- `chk_mw_one_time`: `schedule_type='ONE_TIME'` ⇒ `starts_at` AND `ends_at` NOT NULL
- `chk_mw_recurring`: `schedule_type='RECURRING'` ⇒ `cron_expr` AND `duration_minutes` NOT NULL
- `chk_mw_window_positive`: ONE_TIME ⇒ `ends_at > starts_at`; RECURRING ⇒ `duration_minutes > 0`

### `created_by` is NOT NULL — tests must seed a real user

Unlike `alert_routing`, `maintenance_windows.created_by` is a non-nullable FK to
`users`. The route must set `created_by` to the authenticated user's id, and that
user **must exist** in the DB or the insert fails. Every POST test therefore has
to seed a `User` row first and mint the JWT with that user's id. (Contrast with
`routing.py`, which nulls a missing actor — that path is not available here.)

### Cache invalidation is cross-process — DECISION REQUIRED (see Open Questions)

`MaintenanceCalendar` (vms/anomaly/maintenance.py) is an **in-memory TTL cache
living in the orchestrator process**, not the API process. The API cannot call
`calendar.invalidate()` directly — there is no shared instance. Spec §D says the
calendar is "refreshed every 30s (or invalidated on POST/PATCH/DELETE)."

Chosen approach (mirrors the `detector_config_changed` pattern from commit
`daad3808`): on every write the API publishes a Redis pub/sub message on channel
`maintenance_calendar_changed`. The 30s TTL (`maintenance_cache_ttl_s`) remains
the correctness backstop and already guarantees eventual consistency today. The
orchestrator-side **subscription** that turns this into instant invalidation is
NOT in scope here (the orchestrator does not yet subscribe to any config
channels) — it is tracked as a follow-up. See Open Questions Q2.

---

## Open Questions (resolve with user BEFORE implementing)

1. **Authorization role.** Spec §G lists "maintenance window CRUD" as an audited
   operator action but does not pin the role. Recommendation: `require_role("admin",
   "manager")` for POST/PATCH/DELETE (consistent with the anomaly-detectors PATCH);
   GET list + calendar stay at `get_current_user` (any authenticated role).
2. **Cache invalidation depth.** Confirm the Redis-publish + 30s-TTL approach is
   acceptable for this plan, with the orchestrator subscriber deferred to a tracked
   follow-up. Alternative: wire the subscriber now (larger scope, touches the
   orchestrator loop).
3. **`suppress_alert_types` response shape.** The existing `MaintenanceWindowResponse`
   returns it as the raw JSON **string** (`str | None`). Keep as-is for consistency,
   or parse to `list[str] | None` in responses? Recommendation: keep the raw string
   to avoid changing the existing GET contract.
4. **Calendar `from`/`to` required?** Recommendation: both required query params
   (datetime). Reject `to <= from` with 422.

---

## TASK 1 — POST /api/maintenance

**Goal:** Create a maintenance window with full cross-field validation, audit, and
cache invalidation.

### Schema (vms/api/schemas.py) — new `MaintenanceWindowCreate`
- `name: str` (max 200)
- `scope_type: str` — `field_validator` ∈ {`CAMERA`, `ZONE`}
- `scope_id: int`
- `schedule_type: str` — `field_validator` ∈ {`ONE_TIME`, `RECURRING`}
- `starts_at: datetime | None = None`
- `ends_at: datetime | None = None`
- `cron_expr: str | None = None` (max 100)
- `duration_minutes: int | None = None`
- `suppress_alert_types: list[str] | None = None` (None = suppress all)
- `reason: str | None = None` (max 500)
- `model_validator(mode="after")` mirroring the DB CHECKs:
  - ONE_TIME ⇒ `starts_at` and `ends_at` set and `ends_at > starts_at`
  - RECURRING ⇒ `cron_expr` set, `duration_minutes` set and `> 0`, and `cron_expr`
    parses under `croniter` (reuse the same validation the service relies on)

### Route
- `POST /api/maintenance`, `status_code=201`, `response_model=MaintenanceWindowResponse`
- Auth: `require_role("admin", "manager")` (pending Q1)
- Serialize `suppress_alert_types` list → `json.dumps(...)` or `None`
- `created_by` = `int(user["sub"])`
- `write_audit_event(event_type="MAINTENANCE_WINDOW_CREATED", target_type="maintenance_window", target_id=str(window_id), payload=json.dumps({...}))`
- Publish Redis `maintenance_calendar_changed` (helper, see Task 5 / shared)

### Verify steps
1. Add schema → verify: `mypy vms/api/schemas.py` clean
2. Add route → verify: `ruff` + `mypy vms/api/routes/maintenance.py` clean
3. Tests pass (below)

### Tests (tests/test_api_maintenance.py — new file)
- `test_post_maintenance_one_time_succeeds` — seed user; valid ONE_TIME body →
  201, row persisted with `is_active=True`, `created_by` set
- `test_post_maintenance_recurring_succeeds` — valid RECURRING (cron + duration) → 201
- `test_post_maintenance_one_time_missing_starts_at_returns_422` — ONE_TIME with no
  `starts_at` → 422 (validation, not DB 500)
- Mock `get_api_redis` so the publish does not require a live Redis (pattern from
  `test_patch_detector_disable_sets_is_enabled_false`)

**Commit:** `feat: add POST maintenance window endpoint`

---

## TASK 2 — PATCH /api/maintenance/{window_id}

**Goal:** Partial update with the same cross-field validation applied to the
**merged** (existing + patch) state.

### Schema — new `MaintenanceWindowUpdate`
- All fields optional (`name`, `scope_type`, `scope_id`, `schedule_type`,
  `starts_at`, `ends_at`, `cron_expr`, `duration_minutes`, `suppress_alert_types`,
  `reason`, `is_active`)
- Per-field `field_validator`s for enum domains + `duration_minutes > 0` when present
- Cross-field consistency (ONE_TIME/RECURRING coherence) is enforced **in the route**
  against the merged final state, because a partial patch may omit `schedule_type`.
  Document this: load row → apply `model_dump(exclude_unset=True)` → validate merged
  result with a shared helper (extract the Task 1 validator into a reusable function
  callable on a plain object/dict).

### Route
- `PATCH /api/maintenance/{window_id}`, `response_model=MaintenanceWindowResponse`
- Auth: `require_role("admin", "manager")`
- 404 if `db.get(MaintenanceWindow, window_id)` is None
- Apply only `exclude_unset` fields; re-serialize `suppress_alert_types` list → JSON
- `write_audit_event(event_type="MAINTENANCE_WINDOW_UPDATED", ...)` with before/after payload
- Publish `maintenance_calendar_changed`

### Tests
- `test_patch_maintenance_updates_name` — create then patch `name` → 200, name changed
- `test_patch_maintenance_updates_cron` — patch `cron_expr` on a RECURRING window → 200
- `test_patch_maintenance_not_found_returns_404` — PATCH unknown id → 404

**Commit:** `feat: add PATCH maintenance window endpoint`

---

## TASK 3 — DELETE /api/maintenance/{window_id}

**Goal:** Soft-delete (set `is_active=False`); never hard-delete.

### Route
- `DELETE /api/maintenance/{window_id}`, `status_code=204`, `response_class=Response`
- Auth: `require_role("admin", "manager")`
- 404 if window not found
- Set `is_active = False`, commit (do NOT `db.delete`)
- `write_audit_event(event_type="MAINTENANCE_WINDOW_CANCELLED", ...)`
- Publish `maintenance_calendar_changed`
- Note: re-deleting an already-inactive window — spec implies idempotency is fine,
  but the row still exists, so it returns 204 again, not 404. Test asserts the
  **404-on-missing-id** case explicitly (unknown id), and a separate assertion that
  `is_active` is False after the first delete.

### Tests
- `test_delete_maintenance_soft_deletes` — create, delete → 204; row still present,
  `is_active=False`; no longer in `GET /api/maintenance` (which filters active)
- `test_delete_maintenance_unknown_id_returns_404` — DELETE unknown id → 404

**Commit:** `feat: add DELETE maintenance window endpoint`

---

## TASK 4 — GET /api/maintenance/calendar

**Goal:** Gantt-friendly view returning all windows (active **and** inactive)
overlapping `[from, to]`, with RECURRING windows expanded into concrete occurrences.

### Service helper (vms/anomaly/maintenance.py) — new pure function
`expand_occurrences(window, range_from, range_to) -> list[tuple[datetime, datetime]]`
- ONE_TIME: returns `[(starts_at, ends_at)]` if it overlaps the range, else `[]`
- RECURRING: iterate `croniter(cron_expr, range_from)` via `get_next`, each fire
  time `f` yields occurrence `(f, f + timedelta(minutes=duration_minutes))`; include
  while `f <= range_to`; also include the occurrence straddling `range_from` (one
  `get_prev` step) if its end `> range_from`. Guard malformed cron → `[]` + log
  (reuse the existing `CroniterBadCronError`/`ValueError` handling pattern).
- Pure and unit-testable without DB or HTTP.

### Schemas — new
- `MaintenanceCalendarEntry`: `window_id`, `name`, `scope_type`, `scope_id`,
  `schedule_type`, `starts_at: datetime`, `ends_at: datetime`, `is_active`,
  `suppress_alert_types: str | None`, `reason: str | None`
  (for RECURRING, `starts_at`/`ends_at` are the expanded occurrence bounds)
- `MaintenanceCalendarResponse`: `windows: list[MaintenanceCalendarEntry]`

### Route
- `GET /api/maintenance/calendar`, `response_model=MaintenanceCalendarResponse`
- Auth: `get_current_user` (any authenticated role)
- Query params: `from_: datetime = Query(..., alias="from")`, `to: datetime = Query(...)`
- 422 if `to <= from`
- Query ALL windows (no `is_active` filter); for each, call `expand_occurrences`;
  flatten to entries; sort by `starts_at`
- Empty range / no overlap → `{"windows": []}`

### Verify steps
1. Service helper unit tests (no DB) pass
2. Route returns expanded entries for a known RECURRING window
3. `ruff` + `mypy` clean

### Tests
- Service: `test_expand_occurrences_recurring_within_range` — known weekly cron over
  a 3-week range → expected count of occurrences with correct bounds
- Service: `test_expand_occurrences_one_time_outside_range_returns_empty`
- Route: `test_get_calendar_returns_windows_in_range` — seed ONE_TIME + RECURRING,
  query overlapping range → both represented; recurring expanded
- Route: `test_get_calendar_empty_range_returns_empty_list` — range with no windows → `[]`
- Route: `test_get_calendar_rejects_inverted_range` — `to < from` → 422

**Commit:** `feat: add GET maintenance calendar endpoint`

---

## Shared work (do once, in Task 1)

- **Redis publish helper.** Small async helper in the route module (or reuse
  `get_api_redis()` directly as the detector route does):
  `await get_api_redis().publish("maintenance_calendar_changed", json.dumps({"window_id": ...}))`.
  Keep it consistent with `vms/api/routes/anomaly_detectors.py`.
- **Shared validator.** Extract the ONE_TIME/RECURRING coherence check into a single
  function used by both the POST `model_validator` and the PATCH route's merged-state
  check, so the rules live in exactly one place.

## Definition of done (per CLAUDE.md §11, all five endpoints)

- [ ] All four new endpoints implemented; `maintenance.py` now exposes the full
      spec §D surface (GET list, POST, PATCH, DELETE, GET calendar)
- [ ] Each write endpoint: ≥1 positive + ≥1 negative test
- [ ] `pytest tests/test_api_maintenance.py -v` green
- [ ] Full suite green: `pytest`
- [ ] `ruff check vms/ tests/` clean
- [ ] `black vms/ tests/` applied
- [ ] `mypy vms/` strict clean
- [ ] No migration (table pre-exists) — confirm `alembic` untouched
- [ ] Four conventional commits (one per task)
- [ ] CLAUDE.md §3 Known Gaps row for maintenance endpoints marked DONE
- [ ] This plan's Status → COMPLETE

## Out of scope (explicitly NOT in this plan)

- Orchestrator-side subscription to `maintenance_calendar_changed` (follow-up;
  30s TTL is the current backstop)
- The "camera offline — was this expected?" status-badge logic (§D table) — that is
  alert/status-pipeline work, not the CRUD API
- Frontend calendar widget (§D Frontend — Phase 4)
- `alerts.suppressed_by_window_id` wiring (already exists in the model)
