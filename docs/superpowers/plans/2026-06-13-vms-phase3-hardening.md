# Phase 3 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE**

**Goal:** Eight targeted hardening items — Redis stream retry, dispatcher dedup, constraint-violation 422s, SYSTEM_CRITICAL alert cleanup, recalibrate endpoint, readiness probe, logger.exception fixes, and aioredis shutdown.

**Architecture:** Each task is a surgical change to one or two files. Tasks 1–3 are HIGH-priority reliability fixes; Tasks 4–8 are MEDIUM cleanup. Tasks are independent — they can be executed in order or in parallel. Every task follows TDD: failing test first, minimal implementation, passing test, then commit.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.x, redis-py async, Alembic, pytest, fakeredis.

**Spec refs:** v2-hardened-design.md §H.3, §M; production-readiness.md §1; CLAUDE.md §3 Known Gaps.

---

## File Map

| Action | Path |
|---|---|
| Modify | `vms/config.py` — add `redis_stream_retry_attempts`, `redis_stream_retry_delay_ms`, `dead_alerts_stream_maxlen` |
| Modify | `vms/ingestion/worker.py` — add `_stream_add_with_retry` helper |
| Modify | `vms/dispatcher/worker.py` — add dedup check + dead-letter stream write |
| Modify | `vms/api/main.py` — add `SAIntegrityError` exception handler, close Redis in lifespan |
| Modify | `vms/api/routes/cameras.py` — add `POST /cameras/{id}/recalibrate-required` |
| Modify | `vms/api/routes/health.py` — add `GET /ready` |
| Modify | `vms/api/schemas.py` — add `ReadinessResponse` |
| Modify | `vms/db/models.py` — add `recalibrate_required_at` to `Camera` |
| Modify | `vms/scheduler/jobs.py` — fix `logger.error` → `logger.exception` |
| Create | `alembic/versions/<rev>_add_camera_recalibrate_required_at.py` |
| Modify | `docs/superpowers/plans/2026-06-13-vms-phase3-scheduler.md` — replace `UNKNOWN_PERSON` with `SYSTEM_CRITICAL` in Tasks 3–4 code blocks |
| Modify | `CLAUDE.md` §3 — mark `_emit_critical_alert` gap as DONE |
| Modify | `tests/test_ingestion_worker.py` — add stream_add retry tests |
| Modify | `tests/test_dispatcher_worker.py` — add dedup + dead-letter tests |
| Modify | `tests/test_api_main.py` — add IntegrityError → 422 tests, lifespan Redis close test |
| Modify | `tests/api/test_cameras_profile.py` — add recalibrate-required tests |
| Modify | `tests/test_api_health.py` — add readiness probe tests |
| Modify | `tests/scheduler/test_jobs.py` — add `_emit_critical_alert` correctness tests |

---

## Task 1: Redis stream_add retry in ingestion worker (HIGH)

**What is broken:** `vms/ingestion/worker.py:134` calls `await stream_add(...)` with no exception handling. A transient Redis error propagates up through `_capture_loop`, exits the loop, and stops the camera feed silently. The fix is a retry helper with configurable attempts and delay — on final failure, log and drop the frame pointer (the frame is already in SHM; dropping the pointer is far better than killing the loop).

**Files:**
- Modify: `vms/config.py`
- Modify: `vms/ingestion/worker.py`
- Modify: `tests/test_ingestion_worker.py`

- [ ] **Step 1: Write failing tests**

  Append to `tests/test_ingestion_worker.py`:

  ```python
  @pytest.mark.asyncio
  async def test_stream_add_retry_succeeds_on_second_attempt(
      camera_cfg: CameraConfig, fake_redis: AsyncMock
  ) -> None:
      """stream_add transient failure: second attempt succeeds, frame not dropped."""
      worker = IngestionWorker(camera_cfg, fake_redis)
      call_count = 0

      async def flaky_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
          nonlocal call_count
          call_count += 1
          if call_count == 1:
              raise ConnectionError("Redis timeout")
          return "1-0"

      with patch("vms.ingestion.worker.stream_add", side_effect=flaky_stream_add):
          await worker._stream_add_with_retry("frames:group1", {"k": "v"})

      assert call_count == 2


  @pytest.mark.asyncio
  async def test_stream_add_retry_drops_frame_after_max_attempts(
      camera_cfg: CameraConfig, fake_redis: AsyncMock
  ) -> None:
      """All stream_add attempts fail: error is logged, no exception raised."""
      worker = IngestionWorker(camera_cfg, fake_redis)

      async def always_fail(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
          raise ConnectionError("Redis down")

      with (
          patch("vms.ingestion.worker.stream_add", side_effect=always_fail),
          patch("vms.ingestion.worker.logger") as mock_logger,
      ):
          await worker._stream_add_with_retry("frames:group1", {"k": "v"})
          assert mock_logger.exception.called


  @pytest.mark.asyncio
  async def test_stream_add_retry_does_not_kill_capture_loop(
      camera_cfg: CameraConfig, fake_redis: AsyncMock
  ) -> None:
      """Verify the capture loop continues after stream_add failure."""
      frame = np.zeros((48, 64, 3), dtype=np.uint8)
      mock_cap = MagicMock()
      call_count = 0

      def cap_read():  # type: ignore[no-untyped-def]
          nonlocal call_count
          call_count += 1
          if call_count >= 3:
              return False, None   # stop after 2 frames
          return True, frame

      mock_cap.read.side_effect = cap_read
      mock_cap.release = MagicMock()

      stream_add_calls = 0

      async def failing_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
          nonlocal stream_add_calls
          stream_add_calls += 1
          raise ConnectionError("Redis down")

      worker = IngestionWorker(camera_cfg, fake_redis)

      with (
          patch("vms.ingestion.worker.cv2.VideoCapture", return_value=mock_cap),
          patch("vms.ingestion.worker.stream_add", side_effect=failing_stream_add),
          patch("vms.ingestion.worker.SHMSlot.create") as mock_create,
      ):
          mock_slot = MagicMock()
          mock_slot.name = "vms_cam_1"
          mock_slot.write.return_value = 1000
          mock_create.return_value = mock_slot
          await worker.start()

      # Loop processed 2 frames despite stream_add always failing
      assert stream_add_calls >= 2
  ```

- [ ] **Step 2: Run tests to confirm failure**

  ```powershell
  pytest tests/test_ingestion_worker.py::test_stream_add_retry_succeeds_on_second_attempt tests/test_ingestion_worker.py::test_stream_add_retry_drops_frame_after_max_attempts tests/test_ingestion_worker.py::test_stream_add_retry_does_not_kill_capture_loop -v
  ```

  Expected: `FAILED` — `AttributeError: IngestionWorker has no attribute '_stream_add_with_retry'`

- [ ] **Step 3: Add config vars to `vms/config.py`**

  After the `redis_stream_maxlen` line, add:

  ```python
  redis_stream_retry_attempts: int = 3
  redis_stream_retry_delay_ms: int = 100
  ```

- [ ] **Step 4: Add `_stream_add_with_retry` to `IngestionWorker`**

  In `vms/ingestion/worker.py`, add this method inside `IngestionWorker` after `stop()`:

  ```python
  async def _stream_add_with_retry(
      self,
      stream_name: str,
      fields: dict[str, str],
  ) -> None:
      settings = get_settings()
      max_attempts = settings.redis_stream_retry_attempts
      delay_s = settings.redis_stream_retry_delay_ms / 1000.0
      for attempt in range(1, max_attempts + 1):
          try:
              await stream_add(self._redis, stream_name, fields)
              return
          except Exception:
              if attempt == max_attempts:
                  logger.exception(
                      "camera_id=%d stream_add failed after %d attempts; dropping frame seq=%d",
                      self._camera.camera_id,
                      max_attempts,
                      self._seq_id,
                  )
                  return
              logger.warning(
                  "camera_id=%d stream_add attempt %d/%d failed; retrying in %.1fs",
                  self._camera.camera_id,
                  attempt,
                  max_attempts,
                  delay_s,
              )
              await asyncio.sleep(delay_s)
  ```

  Then in `_capture_loop`, replace line 134:
  ```python
  await stream_add(self._redis, stream_name, pointer.to_redis_fields())
  ```
  with:
  ```python
  await self._stream_add_with_retry(stream_name, pointer.to_redis_fields())
  ```

- [ ] **Step 5: Run tests**

  ```powershell
  pytest tests/test_ingestion_worker.py -v
  ```

  Expected: all pass.

- [ ] **Step 6: Lint + type-check**

  ```powershell
  black vms/ingestion/worker.py vms/config.py
  ruff check vms/ingestion/worker.py vms/config.py
  mypy vms/ingestion/worker.py vms/config.py
  ```

  Expected: no errors.

- [ ] **Step 7: Commit**

  ```powershell
  git add vms/ingestion/worker.py vms/config.py tests/test_ingestion_worker.py
  git commit -m "feat: stream_add retry with backoff in IngestionWorker"
  ```

---

## Task 2: AlertDispatcher dedup + dead-letter stream (HIGH)

**What is broken:** Two issues in `vms/dispatcher/worker.py`:
1. **No idempotency check.** On dispatcher restart with cursor reset (e.g. Redis flush), the same alert is dispatched again to every channel. The DB has `AlertDispatch(success=True)` rows that can serve as an idempotency guard.
2. **Dead letters not streamed.** Failed dispatches write an audit event but nothing the `alert_dispatch_dead_letter_drain` scheduler job can poll. The fix adds an `xadd` to a `dead_alerts` stream after all retry attempts are exhausted.

**Files:**
- Modify: `vms/dispatcher/worker.py`
- Modify: `vms/config.py`
- Modify: `tests/test_dispatcher_worker.py`

- [ ] **Step 1: Write failing tests**

  Append to `tests/test_dispatcher_worker.py`:

  ```python
  @pytest.mark.integration
  async def test_dispatcher_skips_already_dispatched_alert(
      db_session: Session,
  ) -> None:
      """Dispatcher skips dispatch if success=True row already exists for (alert_id, channel)."""
      from vms.dispatcher.worker import AlertDispatcher
      from vms.dispatcher.channels import ChannelSender
      from vms.dispatcher.payload import AlertPayload

      cam = _seed_camera(db_session)
      alert = _seed_alert(db_session, cam.camera_id)
      _seed_routing(db_session)

      # Pre-seed a successful dispatch
      existing = AlertDispatch(
          alert_id=alert.alert_id,
          channel="WEBHOOK",
          target="https://example.com/hook",
          attempt_n=1,
          dispatched_at=datetime(2026, 1, 1),
          success=True,
          error=None,
          response_code=None,
      )
      db_session.add(existing)
      db_session.commit()

      redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
      await _publish_alert(redis, cam.camera_id, alert.alert_id)

      send_calls: list[str] = []

      class SpySender:
          async def send(self, payload: AlertPayload, target: str) -> None:
              send_calls.append(target)

      dispatcher = AlertDispatcher(
          redis=redis,
          db_session_factory=lambda: db_session,
          senders={"WEBHOOK": SpySender()},  # type: ignore[arg-type]
      )
      await dispatcher._process_once()

      assert send_calls == [], "Should not re-dispatch already-dispatched alert"


  @pytest.mark.integration
  async def test_dispatcher_writes_dead_alert_to_stream_after_max_retries(
      db_session: Session,
  ) -> None:
      """After all retry attempts fail, alert_id is published to dead_alerts stream."""
      from vms.dispatcher.worker import AlertDispatcher
      from vms.dispatcher.channels import ChannelError, ChannelSender
      from vms.dispatcher.payload import AlertPayload

      cam = _seed_camera(db_session)
      alert = _seed_alert(db_session, cam.camera_id)
      _seed_routing(db_session)
      db_session.commit()

      redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
      await _publish_alert(redis, cam.camera_id, alert.alert_id)

      class AlwaysFailSender:
          async def send(self, payload: AlertPayload, target: str) -> None:
              raise ChannelError("webhook unreachable")

      dispatcher = AlertDispatcher(
          redis=redis,
          db_session_factory=lambda: db_session,
          senders={"WEBHOOK": AlwaysFailSender()},  # type: ignore[arg-type]
          retry_delays=(0, 0, 0),
          max_attempts=3,
      )
      await dispatcher._process_once()

      # Verify dead_alerts stream received the entry
      messages = await redis.xread({"dead_alerts": "0-0"}, count=10)
      assert messages, "Expected an entry in dead_alerts stream"
      _, entries = messages[0]
      _, fields = entries[0]
      assert str(alert.alert_id) == fields["alert_id"]
      assert fields["channel"] == "WEBHOOK"
  ```

- [ ] **Step 2: Run tests to confirm failure**

  ```powershell
  pytest tests/test_dispatcher_worker.py::test_dispatcher_skips_already_dispatched_alert tests/test_dispatcher_worker.py::test_dispatcher_writes_dead_alert_to_stream_after_max_retries -v
  ```

  Expected: `FAILED` — dedup check is absent, dead_alerts stream not written.

- [ ] **Step 3: Add `dead_alerts_stream_maxlen` to `vms/config.py`**

  After `alerts_stream_maxlen`, add:

  ```python
  dead_alerts_stream_maxlen: int = 1_000
  ```

- [ ] **Step 4: Add dedup check to `_dispatch_with_retry`**

  In `vms/dispatcher/worker.py`, modify `_dispatch_with_retry` to check for an existing successful dispatch BEFORE the retry loop:

  ```python
  async def _dispatch_with_retry(
      self,
      db: Session,
      payload: AlertPayload,
      sender: ChannelSender,
      rule: AlertRouting,
  ) -> None:
      """Attempt dispatch up to max_attempts times with exponential backoff."""
      # Idempotency guard: skip if already successfully dispatched for this channel.
      existing = (
          db.query(AlertDispatch)
          .filter_by(alert_id=payload.alert_id, channel=rule.channel, success=True)
          .first()
      )
      if existing is not None:
          logger.debug(
              "alert_id=%d channel=%s already dispatched (dispatch_id=%d); skipping",
              payload.alert_id,
              rule.channel,
              existing.dispatch_id,
          )
          return

      last_error: str | None = None

      for attempt in range(1, self._max_attempts + 1):
          # ... (rest of existing retry loop unchanged)
  ```

- [ ] **Step 5: Write dead-letter stream entry after exhausting retries**

  In `vms/dispatcher/worker.py`, after the `write_audit_event` call at the end of `_dispatch_with_retry` (the dead-letter path), add:

  ```python
  # Publish to dead_alerts stream for scheduler drain job
  try:
      await self._redis.xadd(
          "dead_alerts",
          {
              "alert_id": str(payload.alert_id),
              "channel": rule.channel,
              "target": rule.target,
              "last_error": last_error or "",
          },
          maxlen=get_settings().dead_alerts_stream_maxlen,
      )
  except Exception:
      logger.exception(
          "dead_alerts xadd failed for alert_id=%d channel=%s",
          payload.alert_id,
          rule.channel,
      )
  ```

  Also add `from vms.config import get_settings` if not already imported (it already is via `AlertDispatcher.__init__`).

- [ ] **Step 6: Run tests**

  ```powershell
  pytest tests/test_dispatcher_worker.py -v
  ```

  Expected: all pass.

- [ ] **Step 7: Lint + type-check**

  ```powershell
  black vms/dispatcher/worker.py vms/config.py
  ruff check vms/dispatcher/worker.py vms/config.py
  mypy vms/dispatcher/worker.py vms/config.py
  ```

- [ ] **Step 8: Commit**

  ```powershell
  git add vms/dispatcher/worker.py vms/config.py tests/test_dispatcher_worker.py
  git commit -m "feat: AlertDispatcher dedup guard and dead-letter stream"
  ```

---

## Task 3: DB constraint violations → 422 in all route files (HIGH)

**What is broken:** Every `POST` and `PATCH` route does `db.commit()` without catching `sqlalchemy.exc.IntegrityError`. When a unique constraint fires (e.g. duplicate `employee_id`, duplicate camera name, duplicate routing rule), SQLAlchemy raises `IntegrityError`, which FastAPI wraps as a 500. Clients get an opaque server error for what is clearly a client-side constraint violation. A single global exception handler in `main.py` fixes all routes at once.

**Files:**
- Modify: `vms/api/main.py`
- Modify: `tests/test_api_main.py`
- Modify: `tests/test_api_persons.py`

- [ ] **Step 1: Write failing test for the global handler**

  Append to `tests/test_api_main.py`:

  ```python
  def test_integrity_error_returns_422(db_session: Any) -> None:
      """SAIntegrityError raised by a route becomes HTTP 422, not 500."""
      from fastapi.testclient import TestClient
      from sqlalchemy.exc import IntegrityError as SAIntegrityError
      from vms.api.main import app

      # Patch get_db to yield a session that raises IntegrityError on commit
      def bad_db():  # type: ignore[no-untyped-def]
          class _FakeSession:
              def close(self) -> None:
                  pass
              def add(self, obj: object) -> None:
                  pass
              def commit(self) -> None:
                  raise SAIntegrityError("duplicate key", None, None)
              def rollback(self) -> None:
                  pass
              def refresh(self, obj: object) -> None:
                  pass
          yield _FakeSession()

      from vms.api import deps
      app.dependency_overrides[deps.get_db] = bad_db

      from vms.api.deps import get_current_user
      app.dependency_overrides[get_current_user] = lambda: {"sub": "1", "role": "admin"}

      client = TestClient(app, raise_server_exceptions=False)
      resp = client.post("/api/cameras", json={
          "name": "TestCam", "rtsp_url": "rtsp://x/y", "capability_tier": "FULL",
          "shutter_type": "rolling", "worker_group": 1,
      })
      assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"

      app.dependency_overrides.clear()
  ```

- [ ] **Step 2: Run test to confirm failure**

  ```powershell
  pytest tests/test_api_main.py::test_integrity_error_returns_422 -v
  ```

  Expected: `FAILED` — status code is 500.

- [ ] **Step 3: Add the global exception handler to `vms/api/main.py`**

  Add these imports after the existing imports block:

  ```python
  from fastapi import Request
  from fastapi.responses import JSONResponse
  from sqlalchemy.exc import IntegrityError as SAIntegrityError
  ```

  Add the handler after `app = FastAPI(...)`:

  ```python
  @app.exception_handler(SAIntegrityError)
  async def _integrity_error_handler(request: Request, exc: SAIntegrityError) -> JSONResponse:
      return JSONResponse(status_code=422, content={"detail": "Database constraint violation"})
  ```

- [ ] **Step 4: Run the test**

  ```powershell
  pytest tests/test_api_main.py::test_integrity_error_returns_422 -v
  ```

  Expected: `PASSED`.

- [ ] **Step 5: Write a route-level integration test confirming real duplicate is 422**

  Append to `tests/test_api_persons.py` (open it to see existing fixture patterns first, then add):

  ```python
  @pytest.mark.integration
  def test_create_person_duplicate_employee_id_returns_422(
      client: Any, manager_token: str
  ) -> None:
      """Second POST with same employee_id must return 422, not 500."""
      headers = {"Authorization": f"Bearer {manager_token}"}
      data = {"name": "Alice", "employee_id": "EMP-DUPE-001"}

      r1 = client.post("/api/persons", json=data, headers=headers)
      assert r1.status_code == 201

      r2 = client.post("/api/persons", json=data, headers=headers)
      assert r2.status_code == 422
  ```

- [ ] **Step 6: Run full API tests**

  ```powershell
  pytest tests/test_api_persons.py tests/test_api_main.py -v
  ```

  Expected: all pass.

- [ ] **Step 7: Lint + type-check**

  ```powershell
  black vms/api/main.py
  ruff check vms/api/main.py
  mypy vms/api/main.py
  ```

- [ ] **Step 8: Commit**

  ```powershell
  git add vms/api/main.py tests/test_api_main.py tests/test_api_persons.py
  git commit -m "feat: global SAIntegrityError handler returns 422 across all routes"
  ```

---

## Task 4: _emit_critical_alert redesign — implement /advisor decision (MEDIUM)

**What needs to happen:** The `/advisor` decision was already implemented in commit `c5aa96cd`: `vms/scheduler/jobs.py` uses `alert_type="SYSTEM_CRITICAL"` with `camera_id=None`. The scheduler plan template (`2026-06-13-vms-phase3-scheduler.md`) still shows `UNKNOWN_PERSON`/`camera_id=1` in Task 3 Step 4 and Task 4 Step 3 — update those before anyone executes the scheduler plan. Add tests to lock in the correct behaviour. Update CLAUDE.md §3.

**Files:**
- Modify: `docs/superpowers/plans/2026-06-13-vms-phase3-scheduler.md`
- Modify: `CLAUDE.md` §3
- Modify: `tests/scheduler/test_jobs.py`

- [ ] **Step 1: Write tests verifying the committed `_emit_critical_alert` uses `SYSTEM_CRITICAL` + `camera_id=None`**

  Append to `tests/scheduler/test_jobs.py`:

  ```python
  def test_emit_critical_alert_uses_system_critical_type(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      """_emit_critical_alert must create SYSTEM_CRITICAL alert with camera_id=None."""
      from vms.scheduler.jobs import _emit_critical_alert
      from unittest.mock import MagicMock

      added_alerts: list[object] = []

      mock_session = MagicMock()
      mock_session.__enter__ = lambda s: s
      mock_session.__exit__ = MagicMock(return_value=False)

      def fake_add(obj: object) -> None:
          added_alerts.append(obj)

      mock_session.add = fake_add
      monkeypatch.setattr("vms.scheduler.jobs.SessionLocal", lambda: mock_session)

      _emit_critical_alert(detail="disk full", component="partition_create")

      assert len(added_alerts) == 1
      alert = added_alerts[0]
      assert alert.alert_type == "SYSTEM_CRITICAL", (
          f"Expected SYSTEM_CRITICAL, got {alert.alert_type}"
      )
      assert alert.camera_id is None, (
          f"camera_id must be None for system alerts, got {alert.camera_id}"
      )
      assert alert.severity == "CRITICAL"


  def test_emit_critical_alert_dedup_key_format(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      """dedup_key must be prefixed 'scheduler:' so Guard view filter works correctly."""
      from vms.scheduler.jobs import _emit_critical_alert
      from unittest.mock import MagicMock

      added_alerts: list[object] = []

      mock_session = MagicMock()
      mock_session.__enter__ = lambda s: s
      mock_session.__exit__ = MagicMock(return_value=False)
      mock_session.add = lambda obj: added_alerts.append(obj)
      monkeypatch.setattr("vms.scheduler.jobs.SessionLocal", lambda: mock_session)

      _emit_critical_alert(detail="chain broken at audit_id=5", component="audit_chain_verify")

      assert len(added_alerts) == 1
      key = added_alerts[0].dedup_key
      assert key.startswith("scheduler:"), f"dedup_key must start with 'scheduler:', got {key!r}"


  def test_emit_critical_alert_db_failure_does_not_raise(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      """If the DB write fails, _emit_critical_alert logs and swallows the exception."""
      from vms.scheduler.jobs import _emit_critical_alert
      from unittest.mock import MagicMock

      mock_session = MagicMock()
      mock_session.__enter__ = lambda s: s
      mock_session.__exit__ = MagicMock(return_value=False)
      mock_session.add = MagicMock(side_effect=RuntimeError("DB unavailable"))
      monkeypatch.setattr("vms.scheduler.jobs.SessionLocal", lambda: mock_session)

      # Must not raise
      _emit_critical_alert(detail="test", component="test")
  ```

- [ ] **Step 2: Run tests to confirm they pass (the code is already correct)**

  ```powershell
  pytest tests/scheduler/test_jobs.py::test_emit_critical_alert_uses_system_critical_type tests/scheduler/test_jobs.py::test_emit_critical_alert_dedup_key_format tests/scheduler/test_jobs.py::test_emit_critical_alert_db_failure_does_not_raise -v
  ```

  Expected: all three `PASSED` — the implementation is already correct.

- [ ] **Step 3: Update the scheduler plan to replace `UNKNOWN_PERSON` with `SYSTEM_CRITICAL`**

  Open `docs/superpowers/plans/2026-06-13-vms-phase3-scheduler.md`.

  Find the `_emit_critical_alert` function in Task 3 Step 4 (around line 559):
  ```python
  def _emit_critical_alert(session: Any, *, alert_type: str, detail: str) -> None:
      """Write a synthetic CRITICAL alert to the DB for admin visibility."""
      # Use camera_id=1 as a sentinel (system-wide alert, no specific camera).
      from vms.db.models import Alert as AlertModel
      alert = AlertModel(
          alert_type="UNKNOWN_PERSON",   # re-used as the closest system-alert type
          severity="CRITICAL",
          state="active",
          camera_id=1,
          triggered_at=_utcnow(),
          dedup_key=f"scheduler:{alert_type}:{detail[:40]}",
      )
      session.add(alert)
      session.commit()
  ```

  Replace the entire function body with the standalone version that matches the committed code:
  ```python
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
  ```

  Also find the `_emit_admin_alert` function in Task 4 Step 3 (`runner.py` template, around line 882):
  ```python
  def _emit_admin_alert(job: ScheduledJob, error: str) -> None:
      ...
      alert = AlertModel(
          alert_type="UNKNOWN_PERSON",
          severity="CRITICAL",
          state="active",
          camera_id=1,
          ...
      )
  ```
  Replace `alert_type="UNKNOWN_PERSON"` with `alert_type="SYSTEM_CRITICAL"` and `camera_id=1` with `camera_id=None`.

  Also remove Step 3c (the `/advisor` gate) from Task 3 — the decision is resolved.

- [ ] **Step 4: Update CLAUDE.md §3 known gaps**

  In `CLAUDE.md`, find the row:
  ```
  | `_emit_critical_alert` in scheduler reuses `alert_type='UNKNOWN_PERSON'` | §M | **DESIGN DECISION PENDING** — see scheduler plan pre-Task 3 note; resolve via `/advisor` before implementing |
  ```

  Replace it with:
  ```
  | ~~`_emit_critical_alert` in scheduler reuses `alert_type='UNKNOWN_PERSON'`~~ | §M | **DONE** — `SYSTEM_CRITICAL` + `camera_id=NULL` implemented in commit `c5aa96cd`; scheduler plan updated |
  ```

- [ ] **Step 5: Run full scheduler tests**

  ```powershell
  pytest tests/scheduler/ -v
  ```

  Expected: all pass.

- [ ] **Step 6: Commit**

  ```powershell
  git add tests/scheduler/test_jobs.py docs/superpowers/plans/2026-06-13-vms-phase3-scheduler.md CLAUDE.md
  git commit -m "fix: lock in SYSTEM_CRITICAL alert type; update scheduler plan and CLAUDE.md"
  ```

---

## Task 5: POST /cameras/{id}/recalibrate-required endpoint (MEDIUM)

**What is needed:** Spec §H.3 requires `POST /api/cameras/{id}/recalibrate-required` which invalidates homography + profile data and flags the camera for re-profiling. The Camera model has no `recalibrate_required_at` column — that column is needed to record when recalibration was requested, so the Admin UI can surface cameras awaiting re-profiling.

**Files:**
- Modify: `vms/db/models.py`
- Create: `alembic/versions/<rev>_add_camera_recalibrate_required_at.py`
- Modify: `vms/api/routes/cameras.py`
- Modify: `tests/api/test_cameras_profile.py`

- [ ] **Step 1: Write failing test**

  Append to `tests/api/test_cameras_profile.py`:

  ```python
  @pytest.mark.integration
  def test_recalibrate_required_clears_homography_and_profile(
      client: Any, admin_token: str, db_session: Any
  ) -> None:
      """POST recalibrate-required returns 200, clears homography + profile, sets recalibrate_required_at."""
      from vms.db.models import Camera
      import json

      # Create a camera with profile and homography data
      cam = Camera(
          name="CalibCam",
          rtsp_url="rtsp://x/1",
          capability_tier="FULL",
          homography_matrix=json.dumps([[1, 0, 0], [0, 1, 0], [0, 0, 1]]),
          profile_data='{"fps": 25}',
      )
      db_session.add(cam)
      db_session.commit()

      headers = {"Authorization": f"Bearer {admin_token}"}
      resp = client.post(
          f"/api/cameras/{cam.camera_id}/recalibrate-required",
          headers=headers,
      )
      assert resp.status_code == 200, resp.text

      db_session.refresh(cam)
      assert cam.homography_matrix is None
      assert cam.profile_data is None
      assert cam.profiled_at is None
      assert cam.recalibrate_required_at is not None


  @pytest.mark.integration
  def test_recalibrate_required_404_for_missing_camera(
      client: Any, admin_token: str
  ) -> None:
      headers = {"Authorization": f"Bearer {admin_token}"}
      resp = client.post("/api/cameras/99999/recalibrate-required", headers=headers)
      assert resp.status_code == 404


  @pytest.mark.integration
  def test_recalibrate_required_requires_manager_or_admin(
      client: Any, guard_token: str
  ) -> None:
      headers = {"Authorization": f"Bearer {guard_token}"}
      resp = client.post("/api/cameras/1/recalibrate-required", headers=headers)
      assert resp.status_code in (403, 401)
  ```

- [ ] **Step 2: Run tests to confirm failure**

  ```powershell
  pytest tests/api/test_cameras_profile.py::test_recalibrate_required_clears_homography_and_profile tests/api/test_cameras_profile.py::test_recalibrate_required_404_for_missing_camera tests/api/test_cameras_profile.py::test_recalibrate_required_requires_manager_or_admin -v
  ```

  Expected: `FAILED` — 404 from FastAPI (endpoint not defined), or 422 on missing column.

- [ ] **Step 3: Add `recalibrate_required_at` column to `Camera` in `vms/db/models.py`**

  In `vms/db/models.py`, find the `Camera` class and add after `homography_matrix`:

  ```python
  recalibrate_required_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
  ```

  Confirm `datetime` is already imported at the top of the file (it is).

- [ ] **Step 4: Generate and write the Alembic migration**

  ```powershell
  alembic revision -m "add_camera_recalibrate_required_at"
  ```

  Open the generated file and fill in upgrade/downgrade:

  ```python
  def upgrade() -> None:
      op.add_column(
          "cameras",
          sa.Column("recalibrate_required_at", sa.DateTime(), nullable=True),
      )

  def downgrade() -> None:
      op.drop_column("cameras", "recalibrate_required_at")
  ```

- [ ] **Step 5: Apply migration locally**

  ```powershell
  alembic upgrade head
  ```

  Expected: `Running upgrade ... -> <rev>, add_camera_recalibrate_required_at`

- [ ] **Step 6: Add the endpoint to `vms/api/routes/cameras.py`**

  Add after `get_profile`:

  ```python
  @router.post(
      "/cameras/{camera_id}/recalibrate-required",
      response_model=CameraResponse,
  )
  def flag_recalibrate_required(
      camera_id: int,
      db: Session = Depends(get_db),  # noqa: B008
      user: dict[str, Any] = require_role("admin", "manager"),  # noqa: B008
  ) -> Camera:
      cam = _get_camera_or_404(camera_id, db)
      cam.homography_matrix = None
      cam.profile_data = None
      cam.profiled_at = None
      cam.recalibrate_required_at = datetime.now(timezone.utc).replace(tzinfo=None)
      db.commit()
      db.refresh(cam)
      try:
          actor_id: int | None = int(user["sub"])
      except (ValueError, KeyError):
          actor_id = None
      if actor_id is not None and db.get(DBUser, actor_id) is None:
          actor_id = None
      write_audit_event(
          db,
          event_type="CAMERA_RECALIBRATION_REQUIRED",
          actor_user_id=actor_id,
          target_type="camera",
          target_id=str(camera_id),
          payload=json.dumps({"camera_id": camera_id}),
      )
      return cam
  ```

  The imports `datetime`, `timezone`, `json`, `write_audit_event`, `DBUser`, `require_role` are already present in `cameras.py`.

- [ ] **Step 7: Run tests**

  ```powershell
  pytest tests/api/test_cameras_profile.py -v
  ```

  Expected: all pass.

- [ ] **Step 8: Full suite + lint**

  ```powershell
  pytest -x
  black vms/db/models.py vms/api/routes/cameras.py
  ruff check vms/db/models.py vms/api/routes/cameras.py
  mypy vms/db/models.py vms/api/routes/cameras.py
  ```

- [ ] **Step 9: Commit**

  ```powershell
  git add vms/db/models.py vms/api/routes/cameras.py alembic/versions/ tests/api/test_cameras_profile.py
  git commit -m "feat: POST /cameras/{id}/recalibrate-required endpoint + migration"
  ```

---

## Task 6: GET /api/ready readiness probe (MEDIUM)

**What is needed:** Production deployments need a `/ready` probe separate from `/health`. `/health` is a static liveness check. `/ready` verifies DB + Redis connectivity before the load balancer routes traffic — returns 200 when all checks pass, 503 when any fail.

**Files:**
- Modify: `vms/api/routes/health.py`
- Modify: `vms/api/schemas.py`
- Modify: `tests/test_api_health.py`

- [ ] **Step 1: Write failing tests**

  Append to `tests/test_api_health.py`:

  ```python
  def test_ready_returns_200_when_db_and_redis_healthy() -> None:
      """GET /api/ready returns 200 when DB and Redis are reachable."""
      from fastapi.testclient import TestClient
      from unittest.mock import AsyncMock, MagicMock, patch
      from vms.api.main import app
      from vms.api import deps

      mock_db = MagicMock()
      mock_db.execute = MagicMock(return_value=None)
      mock_db.close = MagicMock()

      def fake_get_db():  # type: ignore[no-untyped-def]
          yield mock_db

      mock_redis = AsyncMock()
      mock_redis.ping = AsyncMock(return_value=True)

      app.dependency_overrides[deps.get_db] = fake_get_db
      app.dependency_overrides[deps.get_api_redis] = lambda: mock_redis

      client = TestClient(app)
      resp = client.get("/api/ready")
      assert resp.status_code == 200
      body = resp.json()
      assert body["db"] == "ok"
      assert body["redis"] == "ok"

      app.dependency_overrides.clear()


  def test_ready_returns_503_when_db_unavailable() -> None:
      """GET /api/ready returns 503 when DB is down."""
      from fastapi.testclient import TestClient
      from unittest.mock import AsyncMock, MagicMock
      from vms.api.main import app
      from vms.api import deps

      mock_db = MagicMock()
      mock_db.execute = MagicMock(side_effect=Exception("DB connection refused"))
      mock_db.close = MagicMock()

      def fake_get_db():  # type: ignore[no-untyped-def]
          yield mock_db

      mock_redis = AsyncMock()
      mock_redis.ping = AsyncMock(return_value=True)

      app.dependency_overrides[deps.get_db] = fake_get_db
      app.dependency_overrides[deps.get_api_redis] = lambda: mock_redis

      client = TestClient(app)
      resp = client.get("/api/ready")
      assert resp.status_code == 503
      body = resp.json()
      assert body["db"] != "ok"
      assert body["redis"] == "ok"

      app.dependency_overrides.clear()


  def test_ready_returns_503_when_redis_unavailable() -> None:
      """GET /api/ready returns 503 when Redis is down."""
      from fastapi.testclient import TestClient
      from unittest.mock import AsyncMock, MagicMock
      from vms.api.main import app
      from vms.api import deps

      mock_db = MagicMock()
      mock_db.execute = MagicMock(return_value=None)
      mock_db.close = MagicMock()

      def fake_get_db():  # type: ignore[no-untyped-def]
          yield mock_db

      mock_redis = AsyncMock()
      mock_redis.ping = AsyncMock(side_effect=Exception("Redis connection refused"))

      app.dependency_overrides[deps.get_db] = fake_get_db
      app.dependency_overrides[deps.get_api_redis] = lambda: mock_redis

      client = TestClient(app)
      resp = client.get("/api/ready")
      assert resp.status_code == 503
      body = resp.json()
      assert body["redis"] != "ok"

      app.dependency_overrides.clear()
  ```

- [ ] **Step 2: Run tests to confirm failure**

  ```powershell
  pytest tests/test_api_health.py::test_ready_returns_200_when_db_and_redis_healthy tests/test_api_health.py::test_ready_returns_503_when_db_unavailable tests/test_api_health.py::test_ready_returns_503_when_redis_unavailable -v
  ```

  Expected: `FAILED` — `GET /api/ready` returns 404.

- [ ] **Step 3: Add `ReadinessResponse` to `vms/api/schemas.py`**

  Find the `HealthResponse` class in `vms/api/schemas.py` and add after it:

  ```python
  class ReadinessResponse(BaseModel):
      db: str
      redis: str
  ```

- [ ] **Step 4: Add `GET /ready` to `vms/api/routes/health.py`**

  Replace the entire `vms/api/routes/health.py` with:

  ```python
  """Health and readiness check endpoints."""

  from __future__ import annotations

  from typing import Any

  import redis.asyncio as aioredis
  from fastapi import APIRouter, Depends
  from fastapi.responses import JSONResponse
  from sqlalchemy import text
  from sqlalchemy.orm import Session

  from vms.api.deps import get_api_redis, get_db
  from vms.api.schemas import HealthResponse, ReadinessResponse

  router = APIRouter()


  @router.get("/health", response_model=HealthResponse)
  async def health() -> HealthResponse:
      return HealthResponse(status="ok", version="0.1.0")


  @router.get("/ready")
  async def readiness(
      db: Session = Depends(get_db),  # noqa: B008
      redis: aioredis.Redis = Depends(get_api_redis),  # noqa: B008
  ) -> JSONResponse:
      checks: dict[str, str] = {}

      try:
          db.execute(text("SELECT 1"))
          checks["db"] = "ok"
      except Exception:
          checks["db"] = "error"

      try:
          await redis.ping()
          checks["redis"] = "ok"
      except Exception:
          checks["redis"] = "error"

      all_ok = all(v == "ok" for v in checks.values())
      return JSONResponse(
          content=checks,
          status_code=200 if all_ok else 503,
      )
  ```

- [ ] **Step 5: Run tests**

  ```powershell
  pytest tests/test_api_health.py -v
  ```

  Expected: all pass.

- [ ] **Step 6: Lint + type-check**

  ```powershell
  black vms/api/routes/health.py vms/api/schemas.py
  ruff check vms/api/routes/health.py vms/api/schemas.py
  mypy vms/api/routes/health.py vms/api/schemas.py
  ```

- [ ] **Step 7: Commit**

  ```powershell
  git add vms/api/routes/health.py vms/api/schemas.py tests/test_api_health.py
  git commit -m "feat: GET /api/ready readiness probe — checks DB + Redis"
  ```

---

## Task 7: logger.exception() fix in scheduler/jobs.py (MEDIUM)

**What is broken:** `vms/scheduler/jobs.py:56-62` uses `logger.error("... error=%s", ..., exc)` inside an `except Exception as exc:` block. Passing the exception as a format argument stringifies it, silently discarding the full stack trace. `logger.exception()` attaches the traceback automatically.

**Files:**
- Modify: `vms/scheduler/jobs.py`
- Modify: `tests/scheduler/test_jobs.py`

- [ ] **Step 1: Write a test that verifies a stack trace is logged on DB failure**

  Append to `tests/scheduler/test_jobs.py`:

  ```python
  def test_emit_critical_alert_logs_exception_with_traceback(
      monkeypatch: pytest.MonkeyPatch,
  ) -> None:
      """logger.exception must be used so the stack trace is captured."""
      from vms.scheduler.jobs import _emit_critical_alert
      from unittest.mock import MagicMock, patch

      mock_session = MagicMock()
      mock_session.__enter__ = lambda s: s
      mock_session.__exit__ = MagicMock(return_value=False)
      mock_session.add = MagicMock(side_effect=RuntimeError("boom"))
      monkeypatch.setattr("vms.scheduler.jobs.SessionLocal", lambda: mock_session)

      with patch("vms.scheduler.jobs.logger") as mock_logger:
          _emit_critical_alert(detail="test", component="test")
          # logger.exception (not logger.error) must be called to capture the traceback
          assert mock_logger.exception.called, "Expected logger.exception, not logger.error"
          assert not mock_logger.error.called, "logger.error should not be used in except block"
  ```

- [ ] **Step 2: Run test to confirm failure**

  ```powershell
  pytest tests/scheduler/test_jobs.py::test_emit_critical_alert_logs_exception_with_traceback -v
  ```

  Expected: `FAILED` — `AssertionError: Expected logger.exception, not logger.error`

- [ ] **Step 3: Fix `_emit_critical_alert` in `vms/scheduler/jobs.py`**

  Find lines 56-62:
  ```python
  except Exception as exc:
      logger.error(
          "_emit_critical_alert: failed to write alert component=%s detail=%s error=%s",
          component,
          detail,
          exc,
      )
  ```

  Replace with:
  ```python
  except Exception:
      logger.exception(
          "_emit_critical_alert: failed to write alert component=%s detail=%s",
          component,
          detail,
      )
  ```

- [ ] **Step 4: Run tests**

  ```powershell
  pytest tests/scheduler/test_jobs.py -v
  ```

  Expected: all pass.

- [ ] **Step 5: Lint + type-check**

  ```powershell
  black vms/scheduler/jobs.py
  ruff check vms/scheduler/jobs.py
  mypy vms/scheduler/jobs.py
  ```

- [ ] **Step 6: Commit**

  ```powershell
  git add vms/scheduler/jobs.py tests/scheduler/test_jobs.py
  git commit -m "fix: use logger.exception in _emit_critical_alert to preserve traceback"
  ```

---

## Task 8: atexit handler for aioredis connection in deps.py (MEDIUM)

**What is broken:** `vms/api/deps.get_api_redis()` creates a process-level `aioredis.Redis` client that is never explicitly closed. On process shutdown, `asyncio` logs `"Unclosed client session"` or similar warnings. The client should be closed in the `lifespan` function's `finally` block in `vms/api/main.py`, where the `AlertDispatcher` is already shut down cleanly.

**Files:**
- Modify: `vms/api/main.py`
- Modify: `tests/test_api_main.py`

- [ ] **Step 1: Write failing test**

  Append to `tests/test_api_main.py`:

  ```python
  @pytest.mark.asyncio
  async def test_lifespan_closes_redis_on_shutdown() -> None:
      """lifespan must call redis.aclose() during shutdown to prevent connection leaks."""
      from contextlib import asynccontextmanager
      from unittest.mock import AsyncMock, MagicMock, patch
      from fastapi import FastAPI

      closed: list[bool] = []

      mock_redis = AsyncMock()
      mock_redis.aclose = AsyncMock(side_effect=lambda: closed.append(True))

      mock_dispatcher = MagicMock()
      mock_dispatcher.run = AsyncMock(side_effect=asyncio.CancelledError)

      with (
          patch("vms.api.main.get_api_redis", return_value=mock_redis),
          patch("vms.api.main.AlertDispatcher") as MockDispatcher,
      ):
          MockDispatcher.from_settings.return_value = mock_dispatcher

          from vms.api.main import lifespan
          test_app = FastAPI(lifespan=lifespan)

          from fastapi.testclient import TestClient
          with TestClient(test_app):
              pass  # enters and exits the lifespan

      assert closed, "redis.aclose() must be called during lifespan shutdown"
  ```

- [ ] **Step 2: Run test to confirm failure**

  ```powershell
  pytest tests/test_api_main.py::test_lifespan_closes_redis_on_shutdown -v
  ```

  Expected: `FAILED` — `AssertionError: redis.aclose() must be called during lifespan shutdown`

- [ ] **Step 3: Add `redis.aclose()` to the `lifespan` finally block in `vms/api/main.py`**

  Find the `lifespan` function (lines 46-65). Replace the `finally` block:

  ```python
  @asynccontextmanager
  async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
      from vms.api.deps import get_api_redis
      from vms.dispatcher.worker import AlertDispatcher

      redis = get_api_redis()
      dispatcher = AlertDispatcher.from_settings(
          redis=redis,
          db_session_factory=SessionLocal,
      )
      task = asyncio.create_task(dispatcher.run(), name="alert-dispatcher")
      try:
          yield
      finally:
          task.cancel()
          try:
              await task
          except asyncio.CancelledError:
              pass
          except Exception:
              logger.exception("AlertDispatcher raised unexpected error during shutdown")
          try:
              await redis.aclose()
          except Exception:
              logger.exception("Error closing Redis connection during shutdown")
  ```

- [ ] **Step 4: Run test**

  ```powershell
  pytest tests/test_api_main.py::test_lifespan_closes_redis_on_shutdown -v
  ```

  Expected: `PASSED`.

- [ ] **Step 5: Full suite regression check**

  ```powershell
  pytest tests/test_api_main.py tests/test_api_health.py tests/test_api_persons.py -v
  ```

  Expected: all pass.

- [ ] **Step 6: Lint + type-check**

  ```powershell
  black vms/api/main.py
  ruff check vms/api/main.py
  mypy vms/api/main.py
  ```

- [ ] **Step 7: Full suite**

  ```powershell
  pytest
  ```

  Expected: no regressions.

- [ ] **Step 8: Commit**

  ```powershell
  git add vms/api/main.py tests/test_api_main.py
  git commit -m "fix: close aioredis connection in lifespan finally block"
  ```

---

## Self-Review — Spec Coverage Check

| Hardening item | Spec ref | Task |
|---|---|---|
| Redis stream_add retry in ingestion worker | CLAUDE.md §12 (reliability) | Task 1 |
| AlertDispatcher dedup (idempotency on replay) | CLAUDE.md §6.3 | Task 2 |
| AlertDispatcher dead-letter stream | v2 §E, scheduler `_alert_dispatch_dead_letter_drain` | Task 2 |
| DB constraint violations → 422 | CLAUDE.md §11 (DoD §8) | Task 3 |
| `_emit_critical_alert` uses `SYSTEM_CRITICAL` | v2 §M, CLAUDE.md §3 | Task 4 |
| `POST /cameras/{id}/recalibrate-required` | v2 §H.3, CLAUDE.md §3 | Task 5 |
| `GET /api/ready` readiness probe | production-readiness.md §1 | Task 6 |
| `logger.exception` in except blocks | CLAUDE.md §5 (no print / logging discipline) | Task 7 |
| aioredis connection closed on shutdown | CLAUDE.md §12 (no resource leaks) | Task 8 |

**Placeholder scan:** No TBD, TODO, "implement later", or "similar to Task N" patterns. All code blocks are complete.

**Type consistency:**
- `_stream_add_with_retry` signature uses `dict[str, str]` matching `stream_add`'s `fields` parameter.
- `flag_recalibrate_required` returns `Camera`, matching `response_model=CameraResponse`.
- `readiness` returns `JSONResponse` (bypasses response_model encoding — correct for variable status codes).
- `_emit_critical_alert` in `jobs.py` uses `*, detail: str, component: str` — matches all call sites.
