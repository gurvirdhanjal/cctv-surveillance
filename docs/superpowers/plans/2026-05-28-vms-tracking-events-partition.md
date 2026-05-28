# VMS `tracking_events` Time-Range Partitioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: NOT STARTED**

**Goal:** Convert `tracking_events` from a plain heap table to a PostgreSQL `PARTITION BY RANGE (event_ts)` table with monthly child partitions. Add a `PartitionManager` utility that creates future partitions at startup and drops old ones. Update the ORM model to reflect the composite PK `(event_id, event_ts)`.

**Architecture:** Single Alembic migration (table reconstruction). New `vms/db/partition_manager.py` module. ORM model update to add `event_ts` to `primary_key=True`. Tests updated to create a current-month partition before any integration test that inserts into `tracking_events`.

**Tech Stack:** PostgreSQL 16 declarative partitioning, SQLAlchemy Core (raw `text()` for DDL in migration), pytest integration markers.

**Spec refs:** `docs/superpowers/specs/2026-05-28-vms-storage-scalability.md` §§ 2.1–2.8

**Prerequisite:** None. Runs independently of the storage abstraction plan. Requires PostgreSQL 12+ (we target 16).

---

## Task 1 — PartitionManager unit tests (RED phase)

Write the tests before implementation so the interface is locked.

- [ ] 1.1 Create `tests/test_db_partition_manager.py`
- [ ] 1.2 `test_ensure_future_partitions_creates_current_month` — call with `months_ahead=0`; assert the table `tracking_events_y{YYYY}m{MM}` exists in `pg_class`
- [ ] 1.3 `test_ensure_future_partitions_creates_n_months_ahead` — call with `months_ahead=2`; assert 3 partitions created (current + 2)
- [ ] 1.4 `test_ensure_future_partitions_is_idempotent` — call twice; assert no error on second call (CREATE TABLE IF NOT EXISTS)
- [ ] 1.5 `test_drop_partitions_before_removes_old_partition` — create a partition for 2 months ago; call `drop_partitions_before` with cutoff = start of last month; assert partition gone from `pg_inherits`
- [ ] 1.6 `test_drop_partitions_before_never_drops_default` — call with very old cutoff; assert `tracking_events_default` still exists
- [ ] 1.7 `test_list_partitions_returns_all_children` — create 2 named partitions + default; list returns all three names
- [ ] 1.8 Mark all tests `@pytest.mark.integration` — require real PostgreSQL
- [ ] 1.9 Run tests → confirm ImportError or AttributeError (module doesn't exist yet) — RED confirmed

---

## Task 2 — Alembic migration: table reconstruction

This migration converts `tracking_events` to a partitioned table.

- [ ] 2.1 Generate: `alembic revision -m "partition_tracking_events_by_event_ts"`
- [ ] 2.2 Write `upgrade()` using `op.execute(text(...))`:
  ```sql
  -- Step 1: rename old table
  ALTER TABLE tracking_events RENAME TO tracking_events_old;

  -- Step 2: create partitioned table
  CREATE TABLE tracking_events (
      event_id    BIGSERIAL,
      camera_id   INTEGER NOT NULL,
      local_track_id VARCHAR(50) NOT NULL,
      global_track_id UUID NOT NULL DEFAULT gen_random_uuid(),
      person_id   INTEGER,
      zone_id     INTEGER,
      event_ts    TIMESTAMP WITHOUT TIME ZONE NOT NULL,
      ingest_ts   TIMESTAMP WITHOUT TIME ZONE NOT NULL,
      bbox_x1     INTEGER NOT NULL,
      bbox_y1     INTEGER NOT NULL,
      bbox_x2     INTEGER NOT NULL,
      bbox_y2     INTEGER NOT NULL,
      floor_x     DOUBLE PRECISION,
      floor_y     DOUBLE PRECISION,
      seq_id      BIGINT NOT NULL,
      CONSTRAINT pk_tracking_events PRIMARY KEY (event_id, event_ts),
      CONSTRAINT chk_bbox_valid CHECK (bbox_x2 > bbox_x1 AND bbox_y2 > bbox_y1),
      CONSTRAINT uq_tracking_idem UNIQUE (camera_id, local_track_id, event_ts),
      CONSTRAINT fk_te_camera FOREIGN KEY (camera_id)
          REFERENCES cameras(camera_id) ON DELETE NO ACTION,
      CONSTRAINT fk_te_person FOREIGN KEY (person_id)
          REFERENCES persons(person_id) ON DELETE SET NULL
  ) PARTITION BY RANGE (event_ts);

  -- Step 3: default partition (safety net)
  CREATE TABLE tracking_events_default
      PARTITION OF tracking_events DEFAULT;

  -- Step 4: current-month partition
  -- Replaced at runtime by PartitionManager; migration creates one for the deploy date
  CREATE TABLE tracking_events_y{YYYY}m{MM}
      PARTITION OF tracking_events
      FOR VALUES FROM ('{month_start}') TO ('{next_month_start}');

  -- Step 5: copy data
  INSERT INTO tracking_events SELECT * FROM tracking_events_old;

  -- Step 6: advance sequence past max existing event_id
  SELECT setval(pg_get_serial_sequence('tracking_events', 'event_id'),
                COALESCE(MAX(event_id), 1))
  FROM tracking_events;

  -- Step 7: indexes on parent (propagate to children automatically)
  CREATE INDEX ix_tracking_events_global_track_id ON tracking_events (global_track_id);
  CREATE INDEX ix_tracking_events_person_id       ON tracking_events (person_id);
  CREATE INDEX ix_tracking_events_camera_id       ON tracking_events (camera_id);
  CREATE INDEX ix_tracking_events_event_ts        ON tracking_events (event_ts);

  -- Step 8: drop old
  DROP TABLE tracking_events_old;
  ```
  Note: generate `{YYYY}`, `{month_start}`, `{next_month_start}` in Python at migration run time using `datetime.now(timezone.utc)`.
- [ ] 2.3 Write `downgrade()`:
  - Create `tracking_events_restored` as plain non-partitioned table (same schema with simple PK `event_id`)
  - `INSERT INTO tracking_events_restored SELECT * FROM tracking_events`
  - Drop `tracking_events` (drops all partitions)
  - Rename `tracking_events_restored` → `tracking_events`
  - Recreate original indexes and constraints
- [ ] 2.4 Run `alembic upgrade head` locally — confirm success
- [ ] 2.5 Run `alembic downgrade -1` — confirm success
- [ ] 2.6 Run `alembic upgrade head` again — round-trip clean
- [ ] 2.7 Run `pytest` — confirm existing test suite still passes

---

## Task 3 — ORM model update

- [ ] 3.1 Update `TrackingEvent` in `vms/db/models.py`:
  - Change `event_id` column: keep `BigInteger, primary_key=True, autoincrement=True`
  - Add `event_ts` to `primary_key=True`: `mapped_column(DateTime, primary_key=True, nullable=False)`
  - The `__table_args__` does not change (constraints unchanged)
- [ ] 3.2 Search codebase for `db.get(TrackingEvent, ...)` — confirm no such pattern exists
- [ ] 3.3 Run `mypy vms/` — clean
- [ ] 3.4 Run `pytest` — all tests pass

---

## Task 4 — PartitionManager implementation (GREEN phase)

- [ ] 4.1 Create `vms/db/partition_manager.py`:
  ```python
  from __future__ import annotations
  import calendar
  from datetime import datetime, timezone
  from sqlalchemy import Engine, text

  def ensure_future_partitions(engine: Engine, months_ahead: int = 3) -> None: ...
  def drop_partitions_before(engine: Engine, cutoff: datetime) -> None: ...
  def list_partitions(engine: Engine) -> list[str]: ...
  ```
- [ ] 4.2 Implement `list_partitions` using `pg_inherits` join:
  ```sql
  SELECT c.relname
  FROM pg_inherits i
  JOIN pg_class c ON c.oid = i.inhrelid
  JOIN pg_class p ON p.oid = i.inhparent
  WHERE p.relname = 'tracking_events'
  ORDER BY c.relname
  ```
- [ ] 4.3 Implement `ensure_future_partitions`:
  - Iterate `range(months_ahead + 1)` months from today
  - For each: compute `year`, `month`, `start_dt`, `end_dt`
  - `CREATE TABLE IF NOT EXISTS tracking_events_y{year:04d}m{month:02d} PARTITION OF tracking_events FOR VALUES FROM ('{start_dt}') TO ('{end_dt}')`
- [ ] 4.4 Implement `drop_partitions_before`:
  - Call `list_partitions`
  - Filter by name pattern `tracking_events_y\d{4}m\d{2}` (skip DEFAULT)
  - Parse year/month from name; compute partition's upper bound
  - If upper bound <= cutoff: `DROP TABLE {name}`
- [ ] 4.5 Run `pytest tests/test_db_partition_manager.py` — GREEN
- [ ] 4.6 Run full `pytest` — all tests pass

---

## Task 5 — Wire PartitionManager into application startup

- [ ] 5.1 Update `vms/db/session.py` (or create `vms/db/startup.py`): export `init_db(engine)` that calls `ensure_future_partitions(engine)` when `VMS_DB_URL` is set and the table exists.
- [ ] 5.2 Call `init_db` from `vms/api/main.py` lifespan handler (or `@app.on_event("startup")`):
  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI) -> AsyncIterator[None]:
      ensure_future_partitions(engine)
      yield
  ```
- [ ] 5.3 Write test `tests/test_api_startup.py`:
  - `test_startup_calls_ensure_future_partitions` — mock `ensure_future_partitions`, start test client, assert called once
- [ ] 5.4 RED → GREEN → pass

---

## Task 6 — Update integration test fixtures

Integration tests that insert into `tracking_events` currently work because the table has no partition constraint. After migration, inserts to the parent succeed (DEFAULT partition), but tests that check partition behaviour explicitly need a named partition.

- [ ] 6.1 In `tests/conftest.py`, add an `autouse` integration fixture:
  ```python
  @pytest.fixture(autouse=True, scope="session")
  def create_test_partition(db_engine) -> None:
      """Ensure a current-month partition exists before integration tests run."""
      from vms.db.partition_manager import ensure_future_partitions
      ensure_future_partitions(db_engine, months_ahead=1)
  ```
- [ ] 6.2 Run `pytest -m integration` — all integration tests pass
- [ ] 6.3 Run full `pytest` — all tests pass

---

## Task 7 — Full verification

- [ ] 7.1 `pytest` — all tests pass (target: ≥ 176 existing + new partition tests)
- [ ] 7.2 `pytest --cov=vms/db/partition_manager --cov-report=term-missing` — ≥ 90% coverage
- [ ] 7.3 `ruff check vms/ tests/` — clean
- [ ] 7.4 `black vms/ tests/` — no changes
- [ ] 7.5 `mypy vms/` — clean
- [ ] 7.6 Verify `alembic upgrade head` + `alembic downgrade base` + `alembic upgrade head` on test DB — round-trip clean
- [ ] 7.7 Update this plan: mark all tasks `[x]`, set `**Status: COMPLETE**`
- [ ] 7.8 Update `CLAUDE.md §3` — note Partitioning complete with commit hash

---

## Acceptance Criteria

- `tracking_events` is `PARTITION BY RANGE (event_ts)` with a DEFAULT partition and at least one monthly partition
- `PartitionManager.ensure_future_partitions` creates month partitions idempotently
- `PartitionManager.drop_partitions_before` never drops the DEFAULT partition
- ORM `TrackingEvent` has composite PK `(event_id, event_ts)`; all existing tests pass without modification
- Application startup calls `ensure_future_partitions` with `months_ahead=3`
- Alembic migration has a working `downgrade()` that restores a plain non-partitioned table
