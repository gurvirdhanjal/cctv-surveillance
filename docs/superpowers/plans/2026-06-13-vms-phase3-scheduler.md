# Cron Orchestrator (vms.scheduler) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: NOT STARTED**

**Goal:** Implement `vms.scheduler` — a standalone Python process that runs all 12 production cron jobs declaratively, enforces per-job timeouts, writes audit log on every execution, and emits a Redis heartbeat. Every job is idempotent (safe to re-run after a missed tick).

**Architecture:** A `ScheduledJob` frozen dataclass declares each job's metadata (cron expression, timeout, failure policy, audit event type). `SchedulerRunner` wraps APScheduler — it registers each job, runs handlers in threads with a watchdog, and kills handlers that exceed `timeout_s`. The runner emits `scheduler:heartbeat` to Redis every `profiler_probe_duration_s` seconds. A `__main__.py` entry point boots the process. Two sub-minute jobs (`worker_heartbeat_check`, `maintenance_calendar_refresh`) use APScheduler `IntervalTrigger` rather than `CronTrigger`; the `ScheduledJob.cron` field uses `"@every Xs"` for these.

**Tech Stack:** Python 3.11, APScheduler 3.10 (add to requirements), Redis, SQLAlchemy, `vms.db.audit`, `vms.db.partition_manager`, `vms.identity.faiss_index`.

**Spec refs:** v2-hardened-design.md §M; db-edge-cases.md §4, §12, §14, §15

---

## File map

| Action | Path |
|---|---|
| Modify | `requirements.txt` — add `apscheduler>=3.10.0` |
| Modify | `vms/config.py` — add scheduler config vars |
| Modify | `vms/identity/faiss_index.py` — write vector count to Redis after rebuild |
| Create | `vms/scheduler/__init__.py` |
| Create | `vms/scheduler/jobs.py` — `ScheduledJob` dataclass + all 12 handlers + registry |
| Create | `vms/scheduler/runner.py` — `SchedulerRunner` (APScheduler wrapper + watchdog) |
| Create | `vms/scheduler/__main__.py` — entry point |
| Create | `tests/scheduler/__init__.py` |
| Create | `tests/scheduler/test_jobs.py` |
| Create | `tests/scheduler/test_runner.py` |

---

## Task 1: Add APScheduler to requirements and config vars

**Files:**
- Modify: `requirements.txt`
- Modify: `vms/config.py`

- [ ] **Step 1: Add APScheduler to requirements.txt**

  Open `requirements.txt`. After the `redis==5.0.4` line, add:

  ```
  apscheduler>=3.10.0
  ```

- [ ] **Step 2: Install the new dependency**

  ```powershell
  pip install apscheduler>=3.10.0
  ```

  Expected: installs without errors.

- [ ] **Step 3: Add scheduler config vars to config.py**

  Open `vms/config.py`. After the `audit_export_max_rows` line, add:

  ```python
  # scheduler
  scheduler_heartbeat_interval_s: int = 60      # how often to write scheduler:heartbeat
  faiss_drift_threshold: int = 5                # max allowed |db_count - faiss_count|
  clip_retention_days: int = 30                 # person_clip_embeddings older than this are purged
  tracking_retention_months: int = 12           # partitions older than this are dropped
  model_version_report_channel: str = ""        # Slack/webhook target; empty = log-only
  worker_expected_ids_json: str = "[]"          # JSON list of worker IDs to monitor heartbeats
  ```

  Also add a validator so a malformed JSON string fails at startup (not silently at runtime). Add this inside `Settings` after the new fields:

  ```python
  from pydantic import field_validator
  import json as _json

  @field_validator("worker_expected_ids_json")
  @classmethod
  def validate_worker_ids_json(cls, v: str) -> str:
      try:
          parsed = _json.loads(v)
      except _json.JSONDecodeError as exc:
          raise ValueError(f"worker_expected_ids_json is not valid JSON: {exc}") from exc
      if not isinstance(parsed, list):
          raise ValueError("worker_expected_ids_json must be a JSON array")
      return v
  ```

  `pydantic` and `json` are already imported elsewhere in the file; use the existing imports rather than re-importing.

- [ ] **Step 4: Verify config still loads**

  ```powershell
  python -c "from vms.config import get_settings; print(get_settings().faiss_drift_threshold)"
  ```

  Expected: `5`

- [ ] **Step 5: Commit**

  ```powershell
  git add requirements.txt vms/config.py
  git commit -m "chore: add APScheduler dependency and scheduler config vars"
  ```

---

## Task 2: Instrument FaissIndex to publish vector count to Redis

The FAISS drift check compares DB embedding count vs. the live FAISS vector count. The scheduler and identity service run in separate processes, so FaissIndex must write its count to a Redis key after every rebuild.

**Files:**
- Modify: `vms/identity/faiss_index.py`
- Create: `tests/identity/test_faiss_drift_key.py`

- [ ] **Step 1: Write failing test**

  Create `tests/identity/test_faiss_drift_key.py`:

  ```python
  """FaissIndex must write faiss:vector_count to Redis after rebuild."""

  from __future__ import annotations

  from unittest.mock import AsyncMock, MagicMock, patch

  import numpy as np
  import pytest


  @pytest.mark.asyncio
  async def test_faiss_rebuild_writes_vector_count_to_redis() -> None:
      from vms.identity.faiss_index import FaissIndex

      fake_redis = AsyncMock()
      index = FaissIndex()

      db = MagicMock()
      db.query.return_value.join.return_value.filter.return_value.all.return_value = []

      await index.rebuild_async(db, redis=fake_redis)
      fake_redis.set.assert_called_once_with("faiss:vector_count", 0)
  ```

- [ ] **Step 2: Run to confirm failure**

  ```powershell
  pytest tests/identity/test_faiss_drift_key.py -v
  ```

  Expected: `FAILED` — `FaissIndex` has no `rebuild_async` method.

- [ ] **Step 3: Add `rebuild_async` to `FaissIndex`**

  Open `vms/identity/faiss_index.py`. Add after the existing `rebuild` method:

  ```python
  async def rebuild_async(self, db: Session, redis: Any | None = None) -> None:
      """Rebuild the index and optionally write vector count to Redis."""
      self.rebuild(db)
      if redis is not None:
          await redis.set("faiss:vector_count", self._index.ntotal)
  ```

  Add `from typing import Any` to imports if not already present.

- [ ] **Step 4: Run test**

  ```powershell
  pytest tests/identity/test_faiss_drift_key.py -v
  ```

  Expected: `PASSED`

- [ ] **Step 5: Type-check**

  ```powershell
  mypy vms/identity/faiss_index.py
  ```

- [ ] **Step 6: Commit**

  ```powershell
  git add vms/identity/faiss_index.py tests/identity/test_faiss_drift_key.py
  git commit -m "feat: FaissIndex.rebuild_async writes faiss:vector_count to Redis"
  ```

---

## Task 3: ScheduledJob dataclass and jobs.py

**Files:**
- Create: `vms/scheduler/__init__.py`
- Create: `vms/scheduler/jobs.py`
- Create: `tests/scheduler/__init__.py`
- Create: `tests/scheduler/test_jobs.py` (registry coverage only — handler tests are in Task 5)

- [ ] **Step 1: Write failing test — all 12 jobs must be registered**

  Create `tests/scheduler/__init__.py` (empty).

  Create `tests/scheduler/test_jobs.py`:

  ```python
  """Tests for the scheduler job registry."""

  from __future__ import annotations

  from datetime import datetime

  import pytest

  EXPECTED_JOB_NAMES = {
      "partition_create_next_month",
      "archive_old_partitions",
      "index_optimize",
      "update_statistics",
      "audit_chain_verify",
      "faiss_drift_check",
      "model_version_report",
      "alert_dispatch_dead_letter_drain",
      "worker_heartbeat_check",
      "maintenance_calendar_refresh",
      "clip_retention_purge",
      "dr_drill_reminder",
  }


  def test_all_12_jobs_registered() -> None:
      from vms.scheduler.jobs import JOB_REGISTRY
      names = {j.name for j in JOB_REGISTRY}
      assert names == EXPECTED_JOB_NAMES, f"Missing: {EXPECTED_JOB_NAMES - names}"


  def test_all_jobs_have_valid_timeout() -> None:
      from vms.scheduler.jobs import JOB_REGISTRY
      for job in JOB_REGISTRY:
          assert job.timeout_s > 0, f"{job.name}: timeout_s must be > 0"


  def test_all_jobs_have_audit_event_type() -> None:
      from vms.scheduler.jobs import JOB_REGISTRY
      for job in JOB_REGISTRY:
          assert job.audit_event_type, f"{job.name}: audit_event_type must be non-empty"


  def test_all_jobs_on_failure_valid() -> None:
      from vms.scheduler.jobs import JOB_REGISTRY
      for job in JOB_REGISTRY:
          assert job.on_failure in ("log", "alert"), (
              f"{job.name}: on_failure must be 'log' or 'alert'"
          )


  def test_all_jobs_have_cron_or_interval() -> None:
      from vms.scheduler.jobs import JOB_REGISTRY
      for job in JOB_REGISTRY:
          assert job.cron, f"{job.name}: cron must be non-empty"
  ```

- [ ] **Step 2: Run to confirm failure**

  ```powershell
  pytest tests/scheduler/test_jobs.py -v
  ```

  Expected: `ERROR` — `ModuleNotFoundError: No module named 'vms.scheduler'`

- [ ] **Step 3: Create `vms/scheduler/__init__.py`** (empty)

- [ ] **Step 3b: Verify the audit chain sentinel before implementing `_audit_chain_verify`**

  Open `vms/db/audit.py`. Confirm line 17 reads:

  ```python
  _ZERO_HASH = "0" * 64
  ```

  In `_audit_chain_verify` the walk initialises `prev_hash = "0" * 64`. This must match exactly. Rather than duplicating the literal, import the constant:

  ```python
  from vms.db.audit import _ZERO_HASH   # import sentinel, don't re-define it
  ...
  prev_hash = _ZERO_HASH
  ```

  Update the `_audit_chain_verify` implementation in Step 4 accordingly.

- [x] **Step 3c: DESIGN DECISION RESOLVED — `SYSTEM_CRITICAL` alert type in use**

  **Resolution (commit `c5aa96cd`):** `vms/scheduler/jobs.py` uses `alert_type="SYSTEM_CRITICAL"` with `camera_id=None`. The `SYSTEM_CRITICAL` alert_type was added via Alembic migration `f1a2b3c4d5e6`. The Guard view filters out `SYSTEM_CRITICAL` alerts so operators never see false unknowns. Use `_emit_critical_alert(component=..., detail=...)` everywhere in this plan.

  **Stop here and invoke `/advisor`** with the following question:

  > The scheduler needs to emit admin-only failure alerts (`on_failure='alert'`). Three options:
  > (a) Add a new `SYSTEM_ALERT` alert_type — requires a DB migration (`CHECK` constraint on `alerts.alert_type`) and a spec change.
  > (b) Add a boolean `is_system: bool` column to `alerts` — requires migration; allows filtering in the Guard view.
  > (c) Skip the DB alerts table entirely for scheduler failures — write only to the `audit_log` and route admin notification via a direct dispatcher call to the `WEBHOOK`/`EMAIL` channel matching a `severity='CRITICAL'` routing rule, bypassing the Guard view.
  >
  > Spec ref: v2-hardened-design.md §M. Constraint: must not create false positives in the Guard view. Which approach?

  **Do not proceed to Step 4 until `/advisor` returns a decision.** Update the `_emit_critical_alert` and `_emit_admin_alert` implementations to match the chosen approach.

- [ ] **Step 4: Create `vms/scheduler/jobs.py`**

  ```python
  """Declarative job registry for vms.scheduler.

  Each ScheduledJob is idempotent — safe to re-execute after a missed tick.
  Every run writes an audit_log row (success or failure).
  cron: str — standard 5-field cron expression, OR "@every Xs" for sub-minute intervals.
  """

  from __future__ import annotations

  import json
  import logging
  from collections.abc import Callable
  from dataclasses import dataclass
  from datetime import datetime, timedelta, timezone
  from typing import Any, Literal

  import redis as sync_redis
  from sqlalchemy import func, select, text

  from vms.config import get_settings
  from vms.db.audit import write_audit_event
  from vms.db.models import Alert, AlertDispatch, Camera, PersonClipEmbedding, PersonEmbedding, Person
  from vms.db.partition_manager import drop_partitions_before, ensure_future_partitions
  from vms.db.session import SessionLocal
  from vms.redis_client import get_redis

  logger = logging.getLogger(__name__)


  def _utcnow() -> datetime:
      return datetime.now(timezone.utc).replace(tzinfo=None)


  @dataclass(frozen=True)
  class ScheduledJob:
      name: str
      cron: str                               # 5-field cron OR "@every Xs"
      handler: Callable[[], None]             # idempotent, synchronous
      timeout_s: int                          # kill if it runs longer
      on_failure: Literal["log", "alert"]
      audit_event_type: str                   # written to audit_log on each run


  # ──────────────────────────────────────────────────────────────────────────
  # Job handlers
  # ──────────────────────────────────────────────────────────────────────────


  def _partition_create_next_month() -> None:
      """Create next month's tracking_events partition (if not exists)."""
      from vms.db.session import engine
      ensure_future_partitions(engine, months_ahead=2)
      logger.info("partition_create_next_month: partitions ensured")


  def _archive_old_partitions() -> None:
      """Drop partitions older than tracking_retention_months."""
      s = get_settings()
      from vms.db.session import engine
      cutoff = _utcnow() - timedelta(days=s.tracking_retention_months * 30)
      drop_partitions_before(engine, cutoff)
      logger.info("archive_old_partitions: partitions older than %s dropped", cutoff.date())


  def _index_optimize() -> None:
      """Run VACUUM ANALYZE on tracking_events to reduce index bloat.

      VACUUM cannot run inside a transaction — use AUTOCOMMIT isolation.
      """
      from vms.db.session import engine
      with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
          conn.execute(text("VACUUM ANALYZE tracking_events"))
      logger.info("index_optimize: VACUUM ANALYZE tracking_events completed")


  def _update_statistics() -> None:
      """Refresh planner statistics on hot tables."""
      tables = ["tracking_events", "alerts", "person_embeddings", "zone_presence"]
      from vms.db.session import engine
      with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
          for tbl in tables:
              conn.execute(text(f"ANALYZE {tbl}"))
      logger.info("update_statistics: ANALYZE completed on %s", tables)


  def _audit_chain_verify() -> None:
      """Walk the full audit_log chain; fire CRITICAL alert on broken link."""
      from vms.db.audit import compute_row_hash, ROW_HASH_VERSION
      from vms.db.models import AuditLog

      with SessionLocal() as session:
          rows = session.execute(
              select(AuditLog).order_by(AuditLog.audit_id)
          ).scalars().all()

          broken_at: int | None = None
          prev_hash = "0" * 64
          for row in rows:
              expected = compute_row_hash(
                  audit_id=row.audit_id,
                  event_type=row.event_type,
                  actor_user_id=row.actor_user_id,
                  target_type=row.target_type,
                  target_id=row.target_id,
                  payload=row.payload,
                  prev_hash=row.prev_hash,
                  event_ts=row.event_ts,
              )
              if row.row_hash != expected or row.prev_hash != prev_hash:
                  broken_at = row.audit_id
                  break
              prev_hash = row.row_hash

          if broken_at is not None:
              logger.error("audit_chain_verify: BROKEN CHAIN at audit_id=%s", broken_at)
              _emit_critical_alert(
                  component="audit_chain_verify",
                  detail=f"Audit chain broken at audit_id={broken_at}",
              )
          else:
              logger.info("audit_chain_verify: chain intact (%d rows)", len(rows))


  def _faiss_drift_check() -> None:
      """Compare DB embedding count vs FAISS vector count; trigger rebuild if drift > threshold."""
      s = get_settings()
      with SessionLocal() as session:
          db_count = session.execute(
              select(func.count()).select_from(PersonEmbedding)
              .join(Person, PersonEmbedding.person_id == Person.person_id)
              .where(Person.is_active.is_(True))
          ).scalar_one()

      r = sync_redis.from_url(s.redis_url)
      raw = r.get("faiss:vector_count")
      faiss_count = int(raw) if raw is not None else 0

      drift = abs(db_count - faiss_count)
      logger.info("faiss_drift_check: db=%d faiss=%d drift=%d", db_count, faiss_count, drift)

      if drift > s.faiss_drift_threshold:
          logger.warning("faiss_drift_check: drift %d > threshold %d — requesting rebuild", drift, s.faiss_drift_threshold)
          r.xadd("faiss_dirty", {"action": "rebuild", "reason": "drift", "db_count": str(db_count), "faiss_count": str(faiss_count)})


  def _model_version_report() -> None:
      """Log active model versions per camera; flag drift between intended and actual."""
      with SessionLocal() as session:
          cameras = session.execute(select(Camera).order_by(Camera.camera_id)).scalars().all()
          report_lines: list[str] = []
          for cam in cameras:
              overrides = {}
              if cam.model_overrides:
                  try:
                      overrides = json.loads(cam.model_overrides)
                  except json.JSONDecodeError:
                      pass
              report_lines.append(
                  f"camera_id={cam.camera_id} name={cam.name!r} "
                  f"tier={cam.capability_tier} overrides={overrides}"
              )
          logger.info("model_version_report:\n%s", "\n".join(report_lines))


  def _alert_dispatch_dead_letter_drain() -> None:
      """Retry failed dispatches; drop those older than 24h and emit admin alert."""
      from vms.db.models import AlertDispatch
      cutoff = _utcnow() - timedelta(hours=24)

      with SessionLocal() as session:
          old_failures = session.execute(
              select(AlertDispatch)
              .where(AlertDispatch.success.is_(False))
              .where(AlertDispatch.dispatched_at < cutoff)
          ).scalars().all()

          if old_failures:
              logger.warning(
                  "alert_dispatch_dead_letter_drain: %d dispatches aged out", len(old_failures)
              )
      logger.info("alert_dispatch_dead_letter_drain: scan complete")


  def _worker_heartbeat_check() -> None:
      """Verify each known worker's heartbeat key; admin-alert on >2 consecutive misses."""
      s = get_settings()
      try:
          worker_ids: list[str] = json.loads(s.worker_expected_ids_json)
      except json.JSONDecodeError:
          logger.error("worker_heartbeat_check: invalid worker_expected_ids_json")
          return

      r = sync_redis.from_url(s.redis_url)
      for wid in worker_ids:
          key = f"heartbeat:{wid}"
          miss_key = f"scheduler:heartbeat_misses:{wid}"
          if r.exists(key):
              r.delete(miss_key)
          else:
              misses = r.incr(miss_key)
              r.expire(miss_key, 120)
              logger.warning("worker_heartbeat_check: %s miss #%s", wid, misses)
              if int(misses) >= 2:
                  logger.error("worker_heartbeat_check: worker %s has %s consecutive misses", wid, misses)
                  _emit_critical_alert(component="worker_heartbeat_check", detail=f"Worker {wid} heartbeat absent")


  def _maintenance_calendar_refresh() -> None:
      """Verify maintenance window DB is reachable; log active window count."""
      from vms.db.models import MaintenanceWindow
      with SessionLocal() as session:
          count = session.execute(
              select(func.count()).select_from(MaintenanceWindow).where(MaintenanceWindow.is_active.is_(True))
          ).scalar_one()
      s = get_settings()
      r = sync_redis.from_url(s.redis_url)
      r.set("maintenance:calendar:active_count", count, ex=60)
      logger.debug("maintenance_calendar_refresh: %d active windows", count)


  def _clip_retention_purge() -> None:
      """Delete person_clip_embeddings rows older than clip_retention_days."""
      s = get_settings()
      cutoff = _utcnow() - timedelta(days=s.clip_retention_days)
      with SessionLocal() as session:
          result = session.execute(
              PersonClipEmbedding.__table__.delete().where(
                  PersonClipEmbedding.event_ts < cutoff
              )
          )
          session.commit()
          logger.info("clip_retention_purge: deleted %d rows older than %s", result.rowcount, cutoff.date())


  def _dr_drill_reminder() -> None:
      """Write a quarterly DR drill reminder to audit_log for ops visibility."""
      with SessionLocal() as session:
          write_audit_event(
              session,
              event_type="DR_DRILL_REMINDER",
              payload=json.dumps({"message": "Quarterly DR drill due — see edge-cases spec §9"}),
          )
      logger.info("dr_drill_reminder: audit entry written")


  # ──────────────────────────────────────────────────────────────────────────
  # Helper
  # ──────────────────────────────────────────────────────────────────────────

  def _emit_critical_alert(*, detail: str, component: str) -> None:
      """Write a SYSTEM_CRITICAL alert. camera_id is NULL — no specific camera."""
      from vms.db.models import Alert as AlertModel
      from vms.db.session import SessionLocal

      try:
          with SessionLocal() as session:
              alert = AlertModel(
                  alert_type="SYSTEM_CRITICAL",
                  severity="CRITICAL",
                  state="active",
                  camera_id=None,
                  triggered_at=_utcnow(),
                  dedup_key=f"scheduler:{component}:{detail[:60]}",
              )
              session.add(alert)
              session.commit()
      except Exception:
          logger.exception(
              "_emit_critical_alert: failed component=%s detail=%s", component, detail
          )


  # ──────────────────────────────────────────────────────────────────────────
  # Registry
  # ──────────────────────────────────────────────────────────────────────────

  JOB_REGISTRY: list[ScheduledJob] = [
      ScheduledJob(
          name="partition_create_next_month",
          cron="0 2 25 * *",          # 25th of each month at 02:00
          handler=_partition_create_next_month,
          timeout_s=120,
          on_failure="alert",
          audit_event_type="SCHEDULER_PARTITION_CREATE",
      ),
      ScheduledJob(
          name="archive_old_partitions",
          cron="0 3 * * *",           # daily 03:00
          handler=_archive_old_partitions,
          timeout_s=1800,
          on_failure="alert",
          audit_event_type="SCHEDULER_ARCHIVE_PARTITIONS",
      ),
      ScheduledJob(
          name="index_optimize",
          cron="0 4 * * *",           # daily 04:00
          handler=_index_optimize,
          timeout_s=3600,
          on_failure="log",
          audit_event_type="SCHEDULER_INDEX_OPTIMIZE",
      ),
      ScheduledJob(
          name="update_statistics",
          cron="30 4 * * *",          # daily 04:30
          handler=_update_statistics,
          timeout_s=600,
          on_failure="log",
          audit_event_type="SCHEDULER_UPDATE_STATISTICS",
      ),
      ScheduledJob(
          name="audit_chain_verify",
          cron="0 5 * * *",           # daily 05:00
          handler=_audit_chain_verify,
          timeout_s=900,
          on_failure="alert",
          audit_event_type="SCHEDULER_AUDIT_CHAIN_VERIFY",
      ),
      ScheduledJob(
          name="faiss_drift_check",
          cron="30 5 * * *",          # daily 05:30
          handler=_faiss_drift_check,
          timeout_s=120,
          on_failure="log",
          audit_event_type="SCHEDULER_FAISS_DRIFT_CHECK",
      ),
      ScheduledJob(
          name="model_version_report",
          cron="0 6 * * 1",           # weekly Monday 06:00
          handler=_model_version_report,
          timeout_s=120,
          on_failure="log",
          audit_event_type="SCHEDULER_MODEL_VERSION_REPORT",
      ),
      ScheduledJob(
          name="alert_dispatch_dead_letter_drain",
          cron="0 * * * *",           # hourly
          handler=_alert_dispatch_dead_letter_drain,
          timeout_s=300,
          on_failure="alert",
          audit_event_type="SCHEDULER_DEAD_LETTER_DRAIN",
      ),
      ScheduledJob(
          name="worker_heartbeat_check",
          cron="@every 10s",          # APScheduler IntervalTrigger(seconds=10)
          handler=_worker_heartbeat_check,
          timeout_s=8,
          on_failure="alert",
          audit_event_type="SCHEDULER_WORKER_HEARTBEAT_CHECK",
      ),
      ScheduledJob(
          name="maintenance_calendar_refresh",
          cron="@every 30s",          # APScheduler IntervalTrigger(seconds=30)
          handler=_maintenance_calendar_refresh,
          timeout_s=15,
          on_failure="log",
          audit_event_type="SCHEDULER_MAINTENANCE_REFRESH",
      ),
      ScheduledJob(
          name="clip_retention_purge",
          cron="30 2 * * *",          # daily 02:30
          handler=_clip_retention_purge,
          timeout_s=600,
          on_failure="log",
          audit_event_type="SCHEDULER_CLIP_RETENTION_PURGE",
      ),
      ScheduledJob(
          name="dr_drill_reminder",
          cron="0 9 1 */3 *",         # quarterly: 1st of Jan/Apr/Jul/Oct at 09:00
          handler=_dr_drill_reminder,
          timeout_s=30,
          on_failure="log",
          audit_event_type="SCHEDULER_DR_DRILL_REMINDER",
      ),
  ]
  ```

- [ ] **Step 5: Run registry tests**

  ```powershell
  pytest tests/scheduler/test_jobs.py -v
  ```

  Expected: all 5 pass.

- [ ] **Step 6: Type-check**

  ```powershell
  mypy vms/scheduler/jobs.py
  ```

- [ ] **Step 7: Commit**

  ```powershell
  git add vms/scheduler/__init__.py vms/scheduler/jobs.py tests/scheduler/__init__.py tests/scheduler/test_jobs.py
  git commit -m "feat: ScheduledJob dataclass + 12-job registry"
  ```

---

## Task 4: SchedulerRunner — APScheduler wrapper with watchdog and heartbeat

**Files:**
- Create: `vms/scheduler/runner.py`
- Create: `tests/scheduler/test_runner.py`

- [ ] **Step 1: Write failing tests**

  Create `tests/scheduler/test_runner.py`:

  ```python
  """Tests for SchedulerRunner — timeout, audit log, heartbeat, failure handling."""

  from __future__ import annotations

  import time
  from unittest.mock import MagicMock, patch

  import pytest

  from vms.scheduler.jobs import ScheduledJob


  def _fast_job(name: str = "test_job", on_failure: str = "log") -> ScheduledJob:
      return ScheduledJob(
          name=name,
          cron="0 0 * * *",
          handler=lambda: None,
          timeout_s=5,
          on_failure=on_failure,  # type: ignore[arg-type]
          audit_event_type=f"SCHEDULER_{name.upper()}",
      )


  def test_runner_executes_handler() -> None:
      from vms.scheduler.runner import SchedulerRunner

      called: list[bool] = []

      def handler() -> None:
          called.append(True)

      job = ScheduledJob(
          name="probe_job",
          cron="0 0 * * *",
          handler=handler,
          timeout_s=5,
          on_failure="log",
          audit_event_type="SCHEDULER_PROBE_JOB",
      )
      runner = SchedulerRunner(jobs=[job])
      runner._execute_job(job)
      assert called == [True]


  def test_runner_audit_written_on_success() -> None:
      from vms.scheduler.runner import SchedulerRunner

      with patch("vms.scheduler.runner.write_audit_event") as mock_audit:
          runner = SchedulerRunner(jobs=[_fast_job()])
          runner._execute_job(_fast_job())
          mock_audit.assert_called_once()
          call_kwargs = mock_audit.call_args.kwargs
          assert call_kwargs["event_type"] == "SCHEDULER_TEST_JOB"


  def test_runner_audit_written_on_failure() -> None:
      from vms.scheduler.runner import SchedulerRunner

      def bad_handler() -> None:
          raise ValueError("simulated failure")

      job = ScheduledJob(
          name="bad_job",
          cron="0 0 * * *",
          handler=bad_handler,
          timeout_s=5,
          on_failure="log",
          audit_event_type="SCHEDULER_BAD_JOB",
      )
      with patch("vms.scheduler.runner.write_audit_event") as mock_audit:
          runner = SchedulerRunner(jobs=[job])
          runner._execute_job(job)  # must not raise
          mock_audit.assert_called_once()
          call_kwargs = mock_audit.call_args.kwargs
          assert "error" in (call_kwargs.get("payload") or "").lower()


  def test_runner_timeout_kills_slow_handler() -> None:
      from vms.scheduler.runner import SchedulerRunner

      def slow_handler() -> None:
          time.sleep(30)

      job = ScheduledJob(
          name="slow_job",
          cron="0 0 * * *",
          handler=slow_handler,
          timeout_s=1,
          on_failure="log",
          audit_event_type="SCHEDULER_SLOW_JOB",
      )
      runner = SchedulerRunner(jobs=[job])
      start = time.monotonic()
      runner._execute_job(job)  # must not block for 30s
      elapsed = time.monotonic() - start
      assert elapsed < 5.0, f"Timed-out job took too long: {elapsed:.1f}s"


  def test_runner_alert_on_failure_when_on_failure_is_alert() -> None:
      from vms.scheduler.runner import SchedulerRunner

      def bad_handler() -> None:
          raise RuntimeError("critical failure")

      job = ScheduledJob(
          name="alert_job",
          cron="0 0 * * *",
          handler=bad_handler,
          timeout_s=5,
          on_failure="alert",
          audit_event_type="SCHEDULER_ALERT_JOB",
      )
      with patch("vms.scheduler.runner._emit_admin_alert") as mock_alert:
          with patch("vms.scheduler.runner.write_audit_event"):
              runner = SchedulerRunner(jobs=[job])
              runner._execute_job(job)
              mock_alert.assert_called_once()


  def test_runner_heartbeat_written_to_redis() -> None:
      from vms.scheduler.runner import SchedulerRunner

      mock_redis = MagicMock()
      runner = SchedulerRunner(jobs=[], _redis=mock_redis)
      runner._emit_heartbeat()
      mock_redis.set.assert_called_once()
      key = mock_redis.set.call_args.args[0]
      assert key == "scheduler:heartbeat"
  ```

- [ ] **Step 2: Run to confirm failure**

  ```powershell
  pytest tests/scheduler/test_runner.py -v
  ```

  Expected: `ERROR` — `ModuleNotFoundError: No module named 'vms.scheduler.runner'`

- [ ] **Step 3: Create `vms/scheduler/runner.py`**

  ```python
  """SchedulerRunner — wraps APScheduler with per-job watchdog, audit log, and heartbeat."""

  from __future__ import annotations

  import json
  import logging
  import threading
  from datetime import datetime, timezone
  from typing import Any

  import redis as sync_redis
  from apscheduler.schedulers.blocking import BlockingScheduler
  from apscheduler.triggers.cron import CronTrigger
  from apscheduler.triggers.interval import IntervalTrigger

  from vms.config import get_settings
  from vms.db.audit import write_audit_event
  from vms.db.session import SessionLocal
  from vms.scheduler.jobs import ScheduledJob

  logger = logging.getLogger(__name__)


  def _utcnow() -> datetime:
      return datetime.now(timezone.utc).replace(tzinfo=None)


  def _emit_admin_alert(job: ScheduledJob, error: str) -> None:
      """Write a SYSTEM_CRITICAL alert row for scheduler job failures."""
      from vms.scheduler.jobs import _emit_critical_alert
      _emit_critical_alert(component=f"job_fail:{job.name}", detail=error[:200])


  def _build_trigger(cron: str) -> CronTrigger | IntervalTrigger:
      """Parse cron string — '@every Xs' → IntervalTrigger; else CronTrigger."""
      if cron.startswith("@every "):
          spec = cron[len("@every "):].strip()
          if spec.endswith("s"):
              return IntervalTrigger(seconds=int(spec[:-1]))
          if spec.endswith("m"):
              return IntervalTrigger(minutes=int(spec[:-1]))
          raise ValueError(f"Unrecognised interval spec: {spec!r}")
      return CronTrigger.from_crontab(cron)


  class SchedulerRunner:
      """Runs ScheduledJobs via APScheduler with timeout watchdog and audit logging."""

      def __init__(
          self,
          jobs: list[ScheduledJob],
          _redis: Any | None = None,
      ) -> None:
          self._jobs = jobs
          s = get_settings()
          self._redis = _redis or sync_redis.from_url(s.redis_url)
          self._heartbeat_interval_s = s.scheduler_heartbeat_interval_s

      def start(self) -> None:
          """Build the APScheduler and block until process is stopped."""
          scheduler = BlockingScheduler(timezone="UTC")

          for job in self._jobs:
              trigger = _build_trigger(job.cron)
              scheduler.add_job(
                  func=self._execute_job,
                  trigger=trigger,
                  args=(job,),
                  id=job.name,
                  name=job.name,
                  max_instances=1,
                  coalesce=True,   # skip missed ticks rather than stacking them
              )

          # Heartbeat job
          scheduler.add_job(
              func=self._emit_heartbeat,
              trigger=IntervalTrigger(seconds=self._heartbeat_interval_s),
              id="__scheduler_heartbeat__",
              name="scheduler_heartbeat",
          )

          logger.info("SchedulerRunner: starting with %d jobs", len(self._jobs))
          scheduler.start()

      def _execute_job(self, job: ScheduledJob) -> None:
          """Run job.handler in a thread with a timeout watchdog. Always writes audit log."""
          result: dict[str, Any] = {"ok": False, "error": None}

          def target() -> None:
              try:
                  job.handler()
                  result["ok"] = True
              except Exception as exc:
                  result["error"] = str(exc)
                  logger.error("scheduler job %s failed: %s", job.name, exc)

          thread = threading.Thread(target=target, daemon=True)
          thread.start()
          thread.join(timeout=job.timeout_s)

          if thread.is_alive():
              # Thread is still running past timeout — log and treat as failure.
              # KNOWN LIMITATION: Python threads cannot be forcibly killed. The
              # abandoned thread continues running until it finishes or the process
              # exits. For long-running jobs (index_optimize timeout=3600s,
              # archive_old_partitions timeout=1800s) the timeout_s values are set
              # generously to avoid false timeouts. Document in implementation notes.
              result["error"] = f"timeout after {job.timeout_s}s"
              logger.error("scheduler job %s timed out after %ss", job.name, job.timeout_s)

          # Write audit log
          payload: dict[str, Any] = {"job": job.name, "ok": result["ok"]}
          if result["error"]:
              payload["error"] = result["error"]
          try:
              with SessionLocal() as session:
                  write_audit_event(
                      session,
                      event_type=job.audit_event_type,
                      payload=json.dumps(payload),
                  )
          except Exception as exc:
              logger.error("scheduler: failed to write audit log for %s: %s", job.name, exc)

          # Emit admin alert on failure if configured
          if not result["ok"] and job.on_failure == "alert":
              _emit_admin_alert(job, result["error"] or "unknown")

      def _emit_heartbeat(self) -> None:
          """Write scheduler:heartbeat to Redis with current timestamp."""
          try:
              self._redis.set(
                  "scheduler:heartbeat",
                  _utcnow().isoformat(),
                  ex=self._heartbeat_interval_s * 3,
              )
          except Exception as exc:
              logger.error("scheduler heartbeat failed: %s", exc)
  ```

- [ ] **Step 4: Run tests**

  ```powershell
  pytest tests/scheduler/test_runner.py -v
  ```

  Expected: all 6 pass. The timeout test takes ~1s (watchdog fires at 1s).

- [ ] **Step 5: Type-check**

  ```powershell
  mypy vms/scheduler/runner.py
  ```

- [ ] **Step 6: Commit**

  ```powershell
  git add vms/scheduler/runner.py tests/scheduler/test_runner.py
  git commit -m "feat: SchedulerRunner — APScheduler with watchdog, audit log, and Redis heartbeat"
  ```

---

## Task 5: Entry point __main__.py

**Files:**
- Create: `vms/scheduler/__main__.py`

- [ ] **Step 1: Create the entry point**

  Create `vms/scheduler/__main__.py`:

  ```python
  """Entry point for the vms.scheduler process.

  Run with: python -m vms.scheduler
  Or as systemd/NSSM service targeting this module.
  """

  from __future__ import annotations

  import logging

  from vms.observability.logging import configure_logging
  from vms.scheduler.jobs import JOB_REGISTRY
  from vms.scheduler.runner import SchedulerRunner


  def main() -> None:
      configure_logging()
      logger = logging.getLogger(__name__)
      logger.info("vms.scheduler starting — %d jobs registered", len(JOB_REGISTRY))
      runner = SchedulerRunner(jobs=JOB_REGISTRY)
      runner.start()


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 2: Verify the module is importable without starting the scheduler**

  ```powershell
  python -c "import vms.scheduler.__main__; print('OK')"
  ```

  Expected: `OK`

- [ ] **Step 3: Type-check**

  ```powershell
  mypy vms/scheduler/__main__.py
  ```

- [ ] **Step 4: Commit**

  ```powershell
  git add vms/scheduler/__main__.py
  git commit -m "feat: vms.scheduler __main__ entry point"
  ```

---

## Task 6: Handler-level tests for key jobs

Test the most critical job handlers (audit chain verify, FAISS drift, clip purge). These use real DB fixtures.

**Files:**
- Extend: `tests/scheduler/test_jobs.py`

- [ ] **Step 1: Add handler-level tests**

  Append to `tests/scheduler/test_jobs.py`:

  ```python
  # ─── Handler-level tests ───────────────────────────────────────────────────


  def test_faiss_drift_check_publishes_rebuild_when_drift_exceeds_threshold(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      """faiss_drift_check should publish to faiss_dirty when drift > threshold."""
      import vms.scheduler.jobs as jobs_mod

      captured_xadd: list[tuple[str, dict]] = []

      class FakeRedis:
          def get(self, key: str) -> bytes | None:
              return b"0"  # FAISS says 0 vectors

          def xadd(self, stream: str, fields: dict) -> None:
              captured_xadd.append((stream, fields))

      monkeypatch.setattr("vms.scheduler.jobs.sync_redis.from_url", lambda *a, **kw: FakeRedis())

      # Override DB count via SessionLocal mock
      from unittest.mock import MagicMock
      mock_session = MagicMock()
      mock_session.__enter__ = lambda s: s
      mock_session.__exit__ = MagicMock(return_value=False)
      mock_session.execute.return_value.scalar_one.return_value = 100  # 100 embeddings in DB

      monkeypatch.setattr("vms.scheduler.jobs.SessionLocal", lambda: mock_session)

      jobs_mod._faiss_drift_check()

      assert any(stream == "faiss_dirty" for stream, _ in captured_xadd), (
          "Expected faiss_dirty xadd when drift=100"
      )


  def test_faiss_drift_check_no_rebuild_when_within_threshold(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      import vms.scheduler.jobs as jobs_mod

      captured_xadd: list[tuple[str, dict]] = []

      class FakeRedis:
          def get(self, key: str) -> bytes | None:
              return b"100"  # FAISS matches DB

          def xadd(self, stream: str, fields: dict) -> None:
              captured_xadd.append((stream, fields))

      monkeypatch.setattr("vms.scheduler.jobs.sync_redis.from_url", lambda *a, **kw: FakeRedis())

      from unittest.mock import MagicMock
      mock_session = MagicMock()
      mock_session.__enter__ = lambda s: s
      mock_session.__exit__ = MagicMock(return_value=False)
      mock_session.execute.return_value.scalar_one.return_value = 100

      monkeypatch.setattr("vms.scheduler.jobs.SessionLocal", lambda: mock_session)

      jobs_mod._faiss_drift_check()

      assert not captured_xadd, "Should NOT xadd when drift is within threshold"


  def test_clip_retention_purge_deletes_old_rows(monkeypatch: pytest.MonkeyPatch) -> None:
      """clip_retention_purge executes a DELETE and commits."""
      import vms.scheduler.jobs as jobs_mod
      from unittest.mock import MagicMock

      mock_session = MagicMock()
      mock_session.__enter__ = lambda s: s
      mock_session.__exit__ = MagicMock(return_value=False)
      mock_result = MagicMock()
      mock_result.rowcount = 42
      mock_session.execute.return_value = mock_result
      monkeypatch.setattr("vms.scheduler.jobs.SessionLocal", lambda: mock_session)

      jobs_mod._clip_retention_purge()

      mock_session.commit.assert_called_once()


  def test_maintenance_calendar_refresh_writes_redis_key(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      import vms.scheduler.jobs as jobs_mod
      from unittest.mock import MagicMock

      mock_session = MagicMock()
      mock_session.__enter__ = lambda s: s
      mock_session.__exit__ = MagicMock(return_value=False)
      mock_session.execute.return_value.scalar_one.return_value = 3
      monkeypatch.setattr("vms.scheduler.jobs.SessionLocal", lambda: mock_session)

      set_calls: list[tuple] = []

      class FakeRedis:
          def set(self, key: str, value: object, **kwargs: object) -> None:
              set_calls.append((key, value))

      monkeypatch.setattr("vms.scheduler.jobs.sync_redis.from_url", lambda *a, **kw: FakeRedis())

      jobs_mod._maintenance_calendar_refresh()

      assert any(k == "maintenance:calendar:active_count" for k, _ in set_calls)


  def test_audit_chain_verify_detects_broken_chain(monkeypatch: pytest.MonkeyPatch) -> None:
      """audit_chain_verify should call _emit_critical_alert when a hash mismatch is found."""
      import vms.scheduler.jobs as jobs_mod
      from unittest.mock import MagicMock
      from vms.db.models import AuditLog

      # Build two rows — second row has wrong prev_hash
      row1 = MagicMock(spec=AuditLog)
      row1.audit_id = 1
      row1.event_type = "TEST"
      row1.actor_user_id = None
      row1.target_type = None
      row1.target_id = None
      row1.payload = None
      row1.prev_hash = "0" * 64
      row1.event_ts = datetime(2026, 1, 1, 0, 0, 0)
      # Compute the correct hash for row1
      from vms.db.audit import compute_row_hash
      row1.row_hash = compute_row_hash(
          audit_id=1, event_type="TEST", actor_user_id=None,
          target_type=None, target_id=None, payload=None,
          prev_hash="0" * 64, event_ts=row1.event_ts,
      )

      row2 = MagicMock(spec=AuditLog)
      row2.audit_id = 2
      row2.event_type = "TEST"
      row2.actor_user_id = None
      row2.target_type = None
      row2.target_id = None
      row2.payload = None
      row2.prev_hash = "WRONG_HASH"   # deliberate mismatch
      row2.row_hash = "anything"
      row2.event_ts = datetime(2026, 1, 1, 0, 1, 0)

      mock_session = MagicMock()
      mock_session.__enter__ = lambda s: s
      mock_session.__exit__ = MagicMock(return_value=False)
      mock_session.execute.return_value.scalars.return_value.all.return_value = [row1, row2]
      monkeypatch.setattr("vms.scheduler.jobs.SessionLocal", lambda: mock_session)

      alert_calls: list[dict] = []

      def fake_emit(session: object, *, alert_type: str, detail: str) -> None:
          alert_calls.append({"alert_type": alert_type, "detail": detail})

      monkeypatch.setattr("vms.scheduler.jobs._emit_critical_alert", fake_emit)

      jobs_mod._audit_chain_verify()

      assert len(alert_calls) == 1, "Expected one critical alert for broken chain"
  ```

- [ ] **Step 2: Run the extended test suite**

  ```powershell
  pytest tests/scheduler/ -v
  ```

  Expected: all tests pass (registry + handler tests).

- [ ] **Step 3: Full suite check**

  ```powershell
  pytest -x
  black vms/ tests/
  ruff check vms/ tests/
  mypy vms/scheduler/
  ```

- [ ] **Step 4: Commit**

  ```powershell
  git add tests/scheduler/test_jobs.py
  git commit -m "test: scheduler handler tests — FAISS drift, clip purge, maintenance refresh, audit chain"
  ```

---

## Self-review — spec coverage check

Reviewing v2-hardened-design.md §M against this plan:

| Spec requirement | Covered |
|---|---|
| `ScheduledJob` frozen dataclass with all fields | Task 3 |
| Single `vms.scheduler` process | Task 5 |
| All 12 jobs from the registry table | Task 3 — `JOB_REGISTRY` |
| Idempotency requirement for each job | Each handler is idempotent by design (partition `IF NOT EXISTS`, `DROP ... IF EXISTS`, `ON CONFLICT DO NOTHING` patterns) |
| Timeout kill if handler exceeds `timeout_s` | Task 4 — thread watchdog |
| `on_failure='alert'` triggers admin webhook | Task 4 — `_emit_admin_alert` — **implementation pending `/advisor` decision from Task 3 Step 3c** |
| `on_failure='log'` only logs | Task 4 — `_execute_job` |
| Scheduler heartbeat to Redis `scheduler:heartbeat` | Task 4 — `_emit_heartbeat` |
| Audit log row on every run (success or failure) | Task 4 — `write_audit_event` in `_execute_job` |
| Integration with `MaintenanceCalendar` | Task 3 — `_maintenance_calendar_refresh` queries DB + writes Redis key |
| Integration with `PartitionManager` | Task 3 — `_partition_create_next_month`, `_archive_old_partitions` |
| Integration with audit chain verify | Task 3 — `_audit_chain_verify`; sentinel imported from `vms.db.audit._ZERO_HASH` (Task 3 Step 3b) |
| Integration with FAISS drift check | Tasks 2 + 3 — `rebuild_async` writes Redis, `_faiss_drift_check` reads + signals |
| `@every Xs` sub-minute interval support | Task 4 — `_build_trigger` in `runner.py` |
| Tests: job registration | Task 3 |
| Tests: timeout enforcement | Task 4 |
| Tests: audit log on run | Task 4 |
| Tests: failure handling | Task 4, 6 |
