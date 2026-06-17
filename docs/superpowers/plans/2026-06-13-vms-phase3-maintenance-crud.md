# Maintenance Window CRUD API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE**

**Goal:** Complete the Maintenance Window REST API per spec §D. The route file
`vms/api/routes/maintenance.py` currently exposes only `GET /api/maintenance`.
This plan adds `POST`, `PATCH`, `DELETE`, and `GET /api/maintenance/calendar`
(4 endpoints), bringing the spec §D surface to full coverage.

**Architecture:** FastAPI routes → SQLAlchemy ORM (`MaintenanceWindow` table,
already migrated, 5 CHECK constraints) → PostgreSQL. Every write appends to
`audit_log` via `write_audit_event()`. Cache invalidation is cross-process via
Redis pub/sub (see Decision 1). The calendar endpoint expands RECURRING windows
server-side using `croniter` (see Decision 2).

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, `croniter` (already a project
dependency — used by `MaintenanceCalendar`), pytest + httpx ASGITransport.

**Spec refs:**
- `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` §D
- `vms/db/models.py` `MaintenanceWindow` (5 CHECK constraints)
- `vms/anomaly/maintenance.py` `MaintenanceCalendar` (invalidate / is_suppressed)
- `vms/api/routes/anomaly_detectors.py` (reference Redis publish pattern)

---

## Architectural Decisions (approved — do not re-open)

### Decision 1 — Cross-process cache invalidation

`MaintenanceCalendar` (in `vms/anomaly/maintenance.py`) is an **in-memory TTL
cache living inside the orchestrator process**, not the API process. The API
cannot call `calendar.invalidate()` directly — there is no shared instance.

**Solution:** After every mutating request (POST, PATCH, DELETE) the API
publishes to Redis pub/sub channel `maintenance_window_changed` with an empty
payload `{}`. The orchestrator-side subscriber that turns this into instant
invalidation is **not in scope for this plan** (tracked as a follow-up); until
that subscriber exists the existing `maintenance_cache_ttl_s = 30` TTL is the
correctness backstop.

**Pattern reference:** `vms/api/routes/anomaly_detectors.py` — `get_api_redis()`
called directly in an `async def` route handler, result awaited for `.publish()`.
Channel name in this plan is `maintenance_window_changed` — a module-level
constant in `maintenance.py`, not a magic string repeated in each handler.

### Decision 2 — Calendar cron expansion

`GET /api/maintenance/calendar` must expand RECURRING windows into concrete
`{starts_at, ends_at}` occurrence slots within `[from, to]`. The frontend
receives ready-to-render slots, not raw cron strings.

**Tool:** `croniter` (already in `pyproject.toml` as a project dependency —
verified by its use in `vms/anomaly/maintenance.py`). Do **not** add it again.

**Algorithm:**
- For ONE_TIME: include if the window's `[starts_at, ends_at]` overlaps `[from, to]`.
- For RECURRING: iterate `croniter(cron_expr, start=from_dt - timedelta(minutes=duration_minutes))`
  forward with `get_next(datetime)` until `occurrence_start > to_dt`. For each
  `occurrence_start`, compute `occurrence_end = occurrence_start + timedelta(minutes=duration_minutes)`.
  Include the slot if `occurrence_end >= from_dt` (catches the window straddling
  `from`). Guard `CroniterBadCronError` / `ValueError` → skip row + log warning.

**Max range:** 90 days, configurable. Add to `vms/config.py`:
```python
maintenance_calendar_max_range_days: int = 90
```
Env var: `VMS_MAINTENANCE_CALENDAR_MAX_RANGE_DAYS`. Return HTTP 400 (not 422)
when `(to - from).days > maintenance_calendar_max_range_days`.

---

## Pre-existing code state — what to keep and what to correct

Commit `e9558a3d` added a working `POST /api/maintenance` endpoint, but with
channel name `maintenance_calendar_changed` (incorrect; must be
`maintenance_window_changed`). It also added several schemas to `schemas.py`.

**Task 1 must begin by:**
1. Reverting the uncommitted import-only edit to `maintenance.py` (the
   `PATCH`-related import additions that were never completed).
2. Correcting the Redis channel constant from `maintenance_calendar_changed`
   to `maintenance_window_changed` in `maintenance.py`.
3. Verifying the POST tests still pass after the channel rename.

No schema rework is needed for Tasks 1–3 — the existing `MaintenanceWindowCreate`
and `MaintenanceWindowUpdate` schemas in `schemas.py` (from the same commit) are
structurally correct. Task 4 will add the calendar-specific response schema.

---

## Model reference (do not re-run migration — table already exists)

`MaintenanceWindow` columns relevant to API validation:

| Column | Type | Constraint | API validation required |
|---|---|---|---|
| `name` | str(200) | NOT NULL | required, max_length=200 |
| `scope_type` | str(20) | `chk_mw_scope` ∈ {CAMERA, ZONE} | field_validator |
| `scope_id` | int | NOT NULL | required |
| `schedule_type` | str(20) | `chk_mw_sched` ∈ {ONE_TIME, RECURRING} | field_validator |
| `starts_at` | datetime\|None | `chk_mw_one_time` if ONE_TIME → NOT NULL | model_validator |
| `ends_at` | datetime\|None | `chk_mw_one_time` if ONE_TIME → NOT NULL | model_validator |
| `cron_expr` | str(100)\|None | `chk_mw_recurring` if RECURRING → NOT NULL | model_validator |
| `duration_minutes` | int\|None | `chk_mw_recurring` if RECURRING → NOT NULL | model_validator |
| `ends_at > starts_at` | — | `chk_mw_window_positive` | model_validator |
| `duration_minutes > 0` | — | `chk_mw_window_positive` | model_validator |
| `created_by` | int FK users | NOT NULL, ondelete=NO ACTION | must use real user_id |
| `suppress_alert_types` | Text\|None | NULL = suppress ALL; else JSON array | serialize list→JSON |
| `reason` | str(500)\|None | — | optional, max_length=500 |

**`created_by` is NOT NULL and a real FK.** Tests seeding a POST must create a
`User` row first and mint the JWT with that user's `user_id`. This is not optional.

---

## TASK 1 — POST /api/maintenance

- [ ] Revert uncommitted import edit; rename channel constant to
      `maintenance_window_changed`; confirm POST tests still pass
- [ ] Schema `MaintenanceWindowCreate` (already in `schemas.py` from commit
      `e9558a3d`) — verify it has all 5 DB constraint mirrors:
      - `field_validator("scope_type")` — ∈ {CAMERA, ZONE}
      - `field_validator("schedule_type")` — ∈ {ONE_TIME, RECURRING}
      - `model_validator(mode="after")` — ONE_TIME ⇒ starts_at + ends_at present
      - `model_validator(mode="after")` — RECURRING ⇒ cron_expr + duration_minutes present
      - `model_validator(mode="after")` — ends_at > starts_at for ONE_TIME
      If any are missing, add them before Task 1 tests run
- [ ] Route `POST /api/maintenance` (already committed) — verify it:
      - Sets `created_by = int(user["sub"])`
      - Serialises `suppress_alert_types: list[str] | None` → `json.dumps` or `None`
      - Calls `write_audit_event(event_type="MAINTENANCE_WINDOW_CREATED", ...)`
      - Publishes to `maintenance_window_changed`
      - Returns 201 + `MaintenanceWindowResponse`
      - Role: `require_role("admin", "manager")`

### Tests (already in `tests/test_api_maintenance.py` from commit `e9558a3d`)
Verify these cover:
- [ ] Valid ONE_TIME window → 201, row in DB with `is_active=True`, `created_by` correct
- [ ] Valid RECURRING window → 201, `cron_expr` and `schedule_type` in response
- [ ] ONE_TIME missing `starts_at` → 422
- [ ] RECURRING missing `cron_expr` → 422 *(add if not present)*
- [ ] `ends_at` before `starts_at` → 422 *(add if not present)*
- [ ] Unauthenticated request → 401 *(add if not present)*
- [ ] Redis publish fires exactly once per POST *(assert `mock.publish.await_count == 1`)*

**Commit:** `feat: add POST maintenance window endpoint`
*(reuse commit message — this is the corrected version of the earlier work)*

---

## TASK 2 — PATCH /api/maintenance/{id}

- [ ] Schema `MaintenanceWindowUpdate` (already in `schemas.py`) — all fields
      optional; per-field validators for `scope_type` / `schedule_type` enums.
      **Cross-field coherence is NOT enforced in the Pydantic schema here** —
      it is enforced in the route after merging existing row + patch fields, so
      a partial patch that omits `schedule_type` still validates correctly
- [ ] Route `PATCH /api/maintenance/{window_id}`:
      - Auth: `require_role("admin", "manager")`
      - `db.get(MaintenanceWindow, window_id)` → 404 if None
      - Merge: load existing row → apply `body.model_dump(exclude_unset=True)`
      - Re-run coherence check on the **merged** state using the shared helper
        `validate_window_coherence(...)` (already in `schemas.py`) — raise 422
        `HTTPException` with detail string if invalid
      - Soft constraint (non-blocking): if `window.is_active` and
        `body.model_dump(exclude_unset=True)` contains fields other than `reason`,
        include `"warning": "window is currently active"` in the response JSON.
        Return this alongside the standard `MaintenanceWindowResponse` fields.
        Simplest implementation: a `MaintenanceWindowPatchResponse` schema that
        extends `MaintenanceWindowResponse` with `warning: str | None = None`,
        and the route populates it. Do not block the write.
      - Serialize `suppress_alert_types` list → JSON string if present in updates
      - Commit, `db.refresh(window)`
      - `write_audit_event(event_type="MAINTENANCE_WINDOW_UPDATED",
          actor_user_id=..., target_type="maintenance_window",
          target_id=str(window_id),
          payload=json.dumps({"changed_fields": {field: {"from": old, "to": new}}}))`
      - Publish `maintenance_window_changed`
      - Return 200 + `MaintenanceWindowPatchResponse`

### Tests (`tests/test_api_maintenance.py`)
- [ ] Update `name` → 200, DB reflects change
- [ ] Update `cron_expr` on a RECURRING window → 200, `cron_expr` changed in response
- [ ] Attempt to set `schedule_type=ONE_TIME` without `starts_at` → 422
- [ ] Non-existent `window_id` → 404
- [ ] Redis publish fires exactly once per PATCH

**Commit:** `feat: add PATCH maintenance window endpoint`

---

## TASK 3 — DELETE /api/maintenance/{id}

- [ ] Route `DELETE /api/maintenance/{window_id}`:
      - Auth: `require_role("admin", "manager")`
      - `db.get(MaintenanceWindow, window_id)` → 404 if None
      - **Also 404 if `window.is_active is False`** — treat already-inactive as
        not found (idempotency is not required here; re-delete is an operator
        error)
      - Set `window.is_active = False` (soft delete — never `db.delete(window)`)
      - Commit
      - `write_audit_event(event_type="MAINTENANCE_WINDOW_CANCELLED",
          actor_user_id=..., target_type="maintenance_window",
          target_id=str(window_id),
          payload=json.dumps({"window_id": window_id, "name": window.name,
                              "reason": "operator_delete"}))`
      - Publish `maintenance_window_changed`
      - Return 204 `Response` (no body)

### Tests (`tests/test_api_maintenance.py`)
- [ ] Delete active window → 204; row still present in DB with `is_active=False`;
      window no longer returned by `GET /api/maintenance`
- [ ] Delete already-inactive window → 404
- [ ] Delete non-existent `window_id` → 404
- [ ] Redis publish fires exactly once per successful DELETE

**Commit:** `feat: add DELETE maintenance window endpoint`

---

## TASK 4 — GET /api/maintenance/calendar

### Config addition (`vms/config.py`)
- [ ] Add under `# maintenance` section:
      ```python
      maintenance_calendar_max_range_days: int = 90
      ```
      Env var: `VMS_MAINTENANCE_CALENDAR_MAX_RANGE_DAYS=90`

### Schema additions (`vms/api/schemas.py`)
- [ ] `CalendarSlot`:
      ```python
      class CalendarSlot(BaseModel):
          window_id: int
          name: str
          scope_type: str
          scope_id: int
          starts_at: datetime
          ends_at: datetime
          is_recurring: bool
          suppress_alert_types: list[str] | None
      ```
      Note: `suppress_alert_types` is returned as a **parsed list** here (not the
      raw JSON string) — the calendar consumer needs to filter by type without
      further parsing.
- [ ] `CalendarResponse`:
      ```python
      class CalendarResponse(BaseModel):
          slots: list[CalendarSlot]
          from_: datetime = Field(..., alias="from")
          to: datetime
          total_slots: int

          model_config = ConfigDict(populate_by_name=True)
      ```

### Route
- [ ] `GET /api/maintenance/calendar`:
      - Auth: `Depends(get_current_user)` (any authenticated role)
      - Query params:
        `from_dt: datetime = Query(..., alias="from")`
        `to_dt: datetime = Query(...)`
      - Validate `to_dt > from_dt` → 422 if not
      - Validate `(to_dt - from_dt).days <= get_settings().maintenance_calendar_max_range_days`
        → **400** (not 422) with `detail="Range exceeds maximum of N days"` if exceeded
      - Fetch `db.query(MaintenanceWindow).filter_by(is_active=True).all()`
      - For each window call `_expand_window(window, from_dt, to_dt)` → `list[CalendarSlot]`
      - Flatten, sort by `starts_at` ascending
      - Return `CalendarResponse(slots=..., from_=from_dt, to=to_dt, total_slots=len(slots))`

### `_expand_window` helper (private, in `maintenance.py`)
Pure function, no DB access, unit-testable independently:

```python
def _expand_window(
    w: MaintenanceWindow, from_dt: datetime, to_dt: datetime
) -> list[CalendarSlot]:
```

- ONE_TIME: if `w.starts_at < to_dt` and `w.ends_at > from_dt` → return 1 slot.
  Else return `[]`.
- RECURRING:
  - Parse `suppress_alert_types` JSON string → `list[str] | None`
  - Iterate from `from_dt - timedelta(minutes=w.duration_minutes)` forward using
    `croniter(w.cron_expr, start_time).get_next(datetime)` until
    `occurrence_start > to_dt`
  - Each slot: `starts_at=occurrence_start`,
    `ends_at=occurrence_start + timedelta(minutes=w.duration_minutes)`
  - Include only if `slot.ends_at > from_dt`
  - Guard: catch `CroniterBadCronError` / `ValueError` → log warning, return `[]`

### Tests (`tests/test_api_maintenance.py`)
- [ ] ONE_TIME window inside range → appears in `slots`, `is_recurring=False`
- [ ] ONE_TIME window entirely outside range → not in `slots`
- [ ] RECURRING window with cron `"0 14 * * 6"` + `duration_minutes=120` over a
      28-day range starting on a Monday → exactly 4 slots returned, all with
      `is_recurring=True` and correct `starts_at`/`ends_at`
- [ ] Range > 90 days → 400
- [ ] No active windows → `{"slots": [], "total_slots": 0, ...}`
- [ ] `to <= from` → 422

**Commit:** `feat: add GET maintenance calendar endpoint`

---

## Definition of done (per CLAUDE.md §11)

Before marking any task complete and before marking this plan COMPLETE:

- [ ] All tests listed under the task pass: `pytest tests/test_api_maintenance.py -v`
- [ ] Full suite passes: `pytest`
- [ ] Lint clean: `ruff check vms/ tests/`
- [ ] Format applied: `black vms/ tests/`
- [ ] Type-check clean: `mypy vms/`
- [ ] Every mutating endpoint: `audit_log` entry verified in at least one test
      (assert via `db_session.query(AuditLog).filter_by(event_type=...).count() == 1`)
- [ ] Redis publish fires on every mutating request — verified by asserting
      `mock_redis.publish.await_count == 1` per test
- [ ] No hardcoded numeric literals: `maintenance_calendar_max_range_days` lives
      in `config.py`; channel name lives as a module constant, not a string literal
- [ ] No migration added or needed (table pre-exists; `alembic history` unchanged)
- [ ] CLAUDE.md §3 Known Open Gaps — remove the maintenance endpoints entry
- [ ] Plan status updated to COMPLETE

---

## Out of scope (do NOT implement in this plan)

- Orchestrator-side `maintenance_window_changed` subscriber (follow-up; 30s TTL
  is the current backstop)
- `GET /api/maintenance?scope_type=&scope_id=&active=` query-param filtering on
  the existing list endpoint (existing behaviour: `filter_by(is_active=True)` only)
- "Camera offline — was this expected?" status-badge logic (§D table)
- Frontend calendar widget (§D Frontend — Phase 4 scope)
- `croniter` dependency declaration — **already present** in `pyproject.toml`
  (confirmed: used by `vms/anomaly/maintenance.py`)
