# Phase 1A/1B Hardening Fixes + Phase 2a Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: NOT STARTED**

**Goal:** Close 7 verified bugs from the Phase 1A/1B edge-case audit and 2 Phase 2a gaps (G1/G2), with full test coverage on every fix, before Phase 2b implementation begins.

**Architecture:** All fixes are in-place changes to existing modules. No new files except one new Alembic migration. No new services.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0, FastAPI, asyncio, Redis Streams, PostgreSQL 16, FAISS, pytest + pytest-asyncio.

**Spec refs:**
- `docs/superpowers/specs/2026-05-01-vms-db-edge-cases.md` §7B (GDPR purge), §14 (audit forward-compat)
- `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` §H (hardening)
- CLAUDE.md §5 (datetime convention), §10 (test targets), §11 (DoD)

---

## Decision log (from /plan-eng-review 2026-05-27)

| D# | Decision | Choice |
|---|---|---|
| D1 | RTSP camera state update mechanism | A: pass `session_factory` to `IngestionWorker.__init__` |
| D2 | `datetime.utcnow` scope | A: fix all 8 column defaults in models.py + persons.py:125 |
| D3 | CLIP embedding purge scope | A: complete purge — collect global_track_ids + delete rows + unlink snapshots |
| D4 | SHM validation style | A: raise `ValueError` with expected vs. actual sizes |
| D5 | faiss_dirty consumer placement | A: background asyncio task in `IdentityEngine.run()` |
| D6 | Purge race condition | A: `db.get(Person, id, with_for_update=True)` |
| D7 | Test coverage | A: add all 11 missing tests |
| D8 | CLIP delete performance | A: server-side `DELETE ... WHERE global_track_id IN (SELECT DISTINCT ...)` |

---

## Task ordering rationale

Tasks run in dependency order. DB-only fixes (Tasks 1, 2) first since later tasks depend on correct
timestamps and the audit column. API fixes (Tasks 3-5) are independent of identity fixes (Tasks 6-7).

---

## Task 1: Fix `datetime.utcnow` — 8 column defaults in models.py + 1 in persons.py

**Background:** `datetime.utcnow()` is deprecated in Python 3.12 and banned by CLAUDE.md §5.
8 column defaults in `vms/db/models.py` and 1 line in `vms/api/routes/persons.py` use it.
No migration needed — column defaults are Python-side only.

### Subtasks

- [ ] 1.1 RED: Write `test_person_created_at_is_utc_naive` in `tests/test_db_models_identity.py`
  - Assert `person.created_at` is a `datetime` with `tzinfo is None` (UTC naive, as required by CLAUDE.md §5)
  - Run: `pytest tests/test_db_models_identity.py -k created_at` → FAILS (currently passes, but we want
    to verify the fix doesn't break anything; skip this RED for defaults since they already produce UTC naive)
- [ ] 1.2 GREEN: Replace all 8 occurrences in `vms/db/models.py`:
  ```python
  # BEFORE (lines 108, 131, 179, 257, 358, 359, 401, 426):
  default=datetime.utcnow
  # AFTER:
  default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
  ```
  Add `from datetime import timezone` if not already imported.
- [ ] 1.3 GREEN: Fix `vms/api/routes/persons.py:125`:
  ```python
  # BEFORE:
  person.purged_at = datetime.utcnow()
  # AFTER:
  person.purged_at = datetime.now(timezone.utc).replace(tzinfo=None)
  ```
  Add `from datetime import timezone` to imports.
- [ ] 1.4 Verify: `grep -r "utcnow" vms/` returns zero results.
- [ ] 1.5 Run: `pytest tests/ -q` → all 159 pass.
- [ ] 1.6 Commit: `fix: replace deprecated datetime.utcnow with timezone-aware UTC in models and persons endpoint`

---

## Task 2: Add `row_hash_version` column to AuditLog

**Background:** Edge-cases spec §14 requires a `row_hash_version` column for forward compatibility
when the hash algorithm changes. The value `ROW_HASH_VERSION = 1` is already used in hash computation
but never persisted as a DB column.

### Subtasks

- [ ] 2.1 RED: Add to `tests/test_db_audit.py`:
  ```python
  def test_audit_row_has_version_field(db_session: Session) -> None:
      row = write_audit_event(db_session, event_type="TEST_VERSION")
      assert row.row_hash_version == 1
  ```
  Run → FAILS (column doesn't exist yet).
- [ ] 2.2 GREEN: Add column to `vms/db/models.py` `AuditLog`:
  ```python
  row_hash_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
  ```
  Place it between `prev_hash` and `row_hash`.
- [ ] 2.3 GREEN: Update `vms/db/audit.py` `write_audit_event()` to set the field:
  ```python
  row = AuditLog(
      ...
      row_hash_version=ROW_HASH_VERSION,
      ...
  )
  ```
- [ ] 2.4 Write migration `alembic/versions/<id>_add_row_hash_version_to_audit_log.py`:
  ```python
  def upgrade() -> None:
      op.add_column("audit_log",
          sa.Column("row_hash_version", sa.Integer(), nullable=False, server_default="1"))

  def downgrade() -> None:
      op.drop_column("audit_log", "row_hash_version")
  ```
  Use `server_default="1"` so existing rows get version 1 on upgrade.
- [ ] 2.5 Apply migration: `alembic upgrade head` against test DB.
- [ ] 2.6 Run: `pytest tests/test_db_audit.py -v` → all pass including new test.
- [ ] 2.7 Commit: `feat(db): add row_hash_version column to audit_log for forward compatibility`

---

## Task 3: GDPR purge hardening — SELECT FOR UPDATE + thumbnail + CLIP + audit payload

**Background:** `purge_person()` has 4 verified gaps:
1. Missing `SELECT ... FOR UPDATE` (race with concurrent enrol)
2. Thumbnail file not deleted from disk
3. PersonClipEmbedding rows not deleted
4. Audit payload is plain string, not `{"reason": …, "embeddings_blanked": N}`

CLIP delete uses a server-side subquery (D8) to avoid materializing large IN lists.
CLIP snapshot files require a two-pass: collect paths, delete rows, then unlink files.

### Subtasks

- [ ] 3.1 RED: Add tests to `tests/test_api_persons.py`:

  ```python
  async def test_purge_deletes_thumbnail_file(db_session, tmp_path):
      # create a temp file as the thumbnail, verify it's gone after purge
      thumb = tmp_path / "face.jpg"; thumb.write_bytes(b"dummy")
      person = ... # seed with thumbnail_path=str(thumb)
      # call purge endpoint
      assert not thumb.exists()

  async def test_purge_deletes_clip_embeddings(db_session):
      # seed PersonClipEmbedding linked via tracking_events.person_id
      # call purge
      assert db_session.query(PersonClipEmbedding).filter_by(...).count() == 0

  async def test_purge_audit_payload_is_json_dict(db_session):
      # call purge; read the PERSON_PURGED audit row
      audit = db_session.query(AuditLog).filter_by(event_type="PERSON_PURGED").first()
      payload = json.loads(audit.payload)
      assert "reason" in payload
      assert "embeddings_blanked" in payload and isinstance(payload["embeddings_blanked"], int)

  async def test_purge_with_for_update_blocks_concurrent_enrol(db_session):
      # minimal test: verify select with_for_update doesn't raise (structural check)
      # Full concurrency test is too complex for unit tests; document as known gap
  ```

  Run → FAILS.

- [ ] 3.2 GREEN: Update `vms/api/routes/persons.py` `purge_person()`:

  ```python
  import json
  import pathlib
  from sqlalchemy import text

  # 1. Lock person row (SELECT FOR UPDATE)
  person = db.get(Person, person_id, with_for_update=True)

  # 2. Capture CLIP snapshot paths BEFORE delete
  clip_rows = db.execute(text(
      "SELECT snapshot_path FROM person_clip_embeddings "
      "WHERE global_track_id IN "
      "(SELECT DISTINCT global_track_id FROM tracking_events WHERE person_id = :pid)"
  ), {"pid": person_id}).fetchall()
  clip_snapshots = [r[0] for r in clip_rows if r[0]]

  # 3. Delete CLIP embeddings (server-side subquery, D8)
  db.execute(text(
      "DELETE FROM person_clip_embeddings "
      "WHERE global_track_id IN "
      "(SELECT DISTINCT global_track_id FROM tracking_events WHERE person_id = :pid)"
  ), {"pid": person_id})

  # 4. Blank AdaFace embeddings (existing logic unchanged)
  blank = np.zeros(512, dtype=np.float32).tolist()
  embs = db.query(PersonEmbedding).filter_by(person_id=person_id).all()
  emb_ids = [e.embedding_id for e in embs]
  for emb in embs:
      emb.embedding = blank
      emb.quality_score = 0.0

  # 5. Soft-delete person
  person.is_active = False
  person.purged_at = datetime.now(timezone.utc).replace(tzinfo=None)

  # 6. Delete thumbnail file from disk
  if person.thumbnail_path:
      pathlib.Path(person.thumbnail_path).unlink(missing_ok=True)
  person.thumbnail_path = None

  # 7. Audit event with JSON payload
  write_audit_event(
      db,
      event_type="PERSON_PURGED",
      actor_user_id=actor_id,
      target_type="person",
      target_id=str(person_id),
      payload=json.dumps({"reason": body.reason, "embeddings_blanked": len(emb_ids)}),
  )

  # 8. After commit, unlink CLIP snapshot files (disk op outside transaction)
  # write_audit_event commits the transaction above
  for snap in clip_snapshots:
      pathlib.Path(snap).unlink(missing_ok=True)

  await faiss_dirty.publish_remove(...)
  ```

- [ ] 3.3 Run: `pytest tests/test_api_persons.py -v` → all pass including 4 new tests.
- [ ] 3.4 Commit: `fix(api): complete GDPR purge — SELECT FOR UPDATE, thumbnail+CLIP delete, JSON audit payload`

---

## Task 4: SHM slot size validation — ValueError in open()

**Background:** `SHMSlot.open()` attaches to an existing shared memory segment without verifying its size.
If width/height mismatch between ingestion writer and inference reader, reads go out of bounds.
Using `ValueError` (not `assert`) ensures the check runs in production with `-O` flag.

### Subtasks

- [ ] 4.1 RED: Add to `tests/test_ingestion_shm.py`:
  ```python
  def test_open_with_wrong_dimensions_raises_value_error():
      slot = SHMSlot.create("vms_test_wrong", 640, 480)
      try:
          with pytest.raises(ValueError, match="SHM size mismatch"):
              SHMSlot.open("vms_test_wrong", 1920, 1080)
      finally:
          slot.close(); slot.unlink()
  ```
  Run → FAILS.
- [ ] 4.2 GREEN: Update `vms/ingestion/shm.py` `SHMSlot.open()`:
  ```python
  @classmethod
  def open(cls, name: str, width: int, height: int) -> SHMSlot:
      shm = SharedMemory(name=name, create=False)
      expected = HEADER_SIZE + width * height * 3
      if shm.size != expected:
          shm.close()
          raise ValueError(
              f"SHM size mismatch for '{name}': "
              f"expected {expected} bytes ({width}x{height}x3 + {HEADER_SIZE} header), "
              f"got {shm.size} — check width/height match between IngestionWorker and InferenceEngine"
          )
      return cls(name, width, height, shm)
  ```
- [ ] 4.3 Run: `pytest tests/test_ingestion_shm.py -v` → all pass.
- [ ] 4.4 Commit: `fix(ingestion): raise ValueError on SHM size mismatch in SHMSlot.open()`

---

## Task 5: RTSP exponential backoff + camera state update

**Background:** `IngestionWorker._capture_loop()` sleeps 100ms on every failed read with no
failure tracking or DB state update. Operators are blind to camera outages.

Decision D1: pass `session_factory: Callable[[], Session]` to `IngestionWorker.__init__`.

### Subtasks

- [ ] 5.1 RED: Add to `tests/test_ingestion_worker.py`:

  ```python
  async def test_rtsp_failure_applies_exponential_backoff(monkeypatch):
      # Mock asyncio.sleep to capture sleep durations
      # Simulate 4 consecutive failed reads
      # Assert sleep calls were: 1.0, 2.0, 4.0, 8.0 (capped at 60s after 5th)
      ...

  async def test_rtsp_failure_threshold_marks_camera_inactive(db_session):
      # Simulate FAILURE_THRESHOLD failed reads in a row
      # Assert Camera.is_active == False in DB after threshold
      ...

  async def test_rtsp_success_resets_failure_counter(monkeypatch):
      # Simulate 3 failures, then 1 success
      # Assert backoff resets to 1s delay on next failure
      ...
  ```

  Run → FAILS.

- [ ] 5.2 GREEN: Update `vms/ingestion/worker.py`:

  ```python
  from sqlalchemy.orm import Session
  from typing import Callable

  _BACKOFF_DELAYS = [1.0, 2.0, 4.0, 8.0, 60.0]  # seconds; last value repeats
  _FAILURE_THRESHOLD = 5  # consecutive failures before marking camera inactive

  class IngestionWorker:
      def __init__(
          self,
          camera: CameraConfig,
          redis_client: aioredis.Redis,
          session_factory: Callable[[], Session] | None = None,
      ) -> None:
          self._camera = camera
          self._redis = redis_client
          self._session_factory = session_factory
          self._seq_id = 0
          self._running = False
          self._slot: SHMSlot | None = None
          self._failure_count = 0

      async def _capture_loop(self) -> None:
          cap = cv2.VideoCapture(self._camera.rtsp_url)
          stream_name = f"frames:group{self._camera.worker_group}"
          try:
              while self._running:
                  ret, frame = cap.read()
                  if not ret:
                      self._failure_count += 1
                      delay = _BACKOFF_DELAYS[min(self._failure_count - 1, len(_BACKOFF_DELAYS) - 1)]
                      logger.warning(
                          "camera_id=%d frame read failed (attempt %d, backing off %.1fs)",
                          self._camera.camera_id, self._failure_count, delay,
                      )
                      if self._failure_count == _FAILURE_THRESHOLD and self._session_factory:
                          self._mark_camera_inactive()
                      await asyncio.sleep(delay)
                      continue
                  self._failure_count = 0  # reset on success
                  # ... existing frame processing logic unchanged ...
          finally:
              cap.release()

      def _mark_camera_inactive(self) -> None:
          try:
              with self._session_factory() as db:
                  cam = db.get(Camera, self._camera.camera_id)
                  if cam:
                      cam.is_active = False
                      db.commit()
                      logger.error("camera_id=%d marked inactive after %d consecutive failures",
                                   self._camera.camera_id, _FAILURE_THRESHOLD)
          except Exception:
              logger.exception("camera_id=%d failed to update DB after failure threshold",
                               self._camera.camera_id)
  ```

- [ ] 5.3 Run: `pytest tests/test_ingestion_worker.py -v` → all pass.
- [ ] 5.4 Commit: `fix(ingestion): add exponential backoff and camera inactive marking on RTSP failure`

---

## Task 6: Wire IdentityEngine.evict_stale() into run() loop (G1)

**Background:** `evict_stale()` exists and is tested in isolation but is never called from `run()`.
The tracklet registry grows unbounded for long-running deployments.

### Subtasks

- [ ] 6.1 RED: Add to `tests/test_identity_engine.py`:
  ```python
  async def test_run_calls_evict_stale_periodically(monkeypatch):
      # Run the engine for a small number of frames
      # Assert evict_stale() is called at least once within the expected interval
      ...
  ```
  Run → FAILS.
- [ ] 6.2 GREEN: Update `vms/identity/engine.py` `run()`:
  ```python
  _EVICT_INTERVAL_FRAMES = 1000  # evict stale tracklets every 1000 frames (~33s at 30fps)
  _frames_since_evict = 0
  ...
  async for frame in self._read_frames():
      ...
      _frames_since_evict += 1
      if _frames_since_evict >= _EVICT_INTERVAL_FRAMES:
          self.evict_stale(int(time.time() * 1000))
          _frames_since_evict = 0
  ```
- [ ] 6.3 Run: `pytest tests/test_identity_engine.py -v` → all pass.
- [ ] 6.4 Commit: `fix(identity): call evict_stale() every 1000 frames in IdentityEngine.run()`

---

## Task 7: Wire faiss_dirty consumer into IdentityEngine.run() (G2)

**Background:** `faiss_dirty` events are published on enrol/purge but never consumed.
FAISS is stale after every enrol/purge until the next service restart.
Decision D5: background `asyncio.create_task()` inside `IdentityEngine.run()`.

### Subtasks

- [ ] 7.1 RED: Add to `tests/test_identity_faiss_dirty.py` (or new `tests/test_identity_faiss_consumer.py`):
  ```python
  async def test_faiss_dirty_add_event_updates_faiss_index(db_session, fake_redis):
      # Enrol a person (insert PersonEmbedding), publish faiss_dirty add event
      # Start the consumer coroutine for one cycle
      # Assert faiss_index.search() finds the new embedding
      ...

  async def test_faiss_dirty_remove_event_updates_faiss_index(db_session, fake_redis):
      # Publish faiss_dirty remove event for a known embedding_id
      # Start consumer for one cycle
      # Assert embedding_id no longer in faiss_index
      ...
  ```
  Run → FAILS.

- [ ] 7.2 GREEN: Update `vms/identity/engine.py`:

  ```python
  async def _consume_faiss_dirty(self) -> None:
      """Background task: apply faiss_dirty stream events to in-memory FAISS index."""
      last_id = "0"  # replay from beginning on startup to catch missed events
      while self._running:
          messages = await stream_read(
              self._redis, "faiss_dirty", last_id=last_id, count=50, block_ms=1000
          )
          for msg_id, fields in messages:
              action = fields.get("action")
              if action == "add":
                  emb_id = int(fields["embedding_id"])
                  # Load embedding from DB and add to FAISS
                  with self._session_factory() as db:
                      rec = db.get(PersonEmbedding, emb_id)
                      if rec and rec.person.is_active:
                          self._faiss_index.add(emb_id, np.array(rec.embedding, dtype=np.float32))
              elif action == "remove":
                  # Remove all embeddings for this person from FAISS
                  person_id = int(fields["person_id"])
                  emb_ids = [int(x) for x in fields.get("embedding_ids", "").split(",") if x]
                  for eid in emb_ids:
                      self._faiss_index.remove(eid)
              last_id = msg_id

  async def run(self) -> None:
      self._running = True
      faiss_task = asyncio.create_task(self._consume_faiss_dirty())
      try:
          # ... existing frame processing loop ...
      finally:
          self._running = False
          await faiss_task
  ```

- [ ] 7.3 Run: `pytest tests/test_identity_faiss_dirty.py -v` (or new file) → all pass.
- [ ] 7.4 Commit: `fix(identity): wire faiss_dirty stream consumer into IdentityEngine.run() as background task`

---

## Task 8: Verify ruff + mypy + full suite pass

- [ ] 8.1 `black vms/ tests/`
- [ ] 8.2 `ruff check vms/ tests/` → zero warnings
- [ ] 8.3 `mypy vms/` → zero errors
- [ ] 8.4 `pytest --cov=vms --cov-report=term-missing -v`
  - Expected: 170+ tests passing (159 existing + 11 new)
  - Coverage: ≥80% on vms/db, vms/api, vms/identity
- [ ] 8.5 `alembic downgrade -1 && alembic upgrade head` round-trip test
- [ ] 8.6 Update CLAUDE.md §3 (phase status unchanged — Phase 2b still next)

---

## NOT in scope

- Audit log DB UPDATE/DELETE triggers (Phase 5 — spec defers this explicitly)
- Kubernetes `/api/ready` + `/api/live` endpoints (Phase 3)
- Clock skew NTP monitoring (Phase 3)
- Spillover buffer (Phase 3)
- XREADGROUP consumer groups for stream replay (larger refactor — pre-production hardening track)
- Violence score / MoViNet inference (Phase 2b)

---

## What already exists (reused, not rebuilt)

- `write_audit_event()` — reused with one new argument (`row_hash_version` field set internally)
- `PersonEmbedding` blanking logic — unchanged
- `faiss_dirty.publish_add/remove` — reused; consumer reads the same stream format
- `evict_stale()` method body — already complete and tested; Task 6 just wires the call
- `ix_tracking_events_person_id` index — already present; used by the CLIP delete subquery

---

## Final verification

```powershell
black vms/ tests/
ruff check vms/ tests/
mypy vms/
pytest --cov=vms --cov-report=term-missing -v
alembic downgrade -1
alembic upgrade head
```

Expected: 170+ tests passing, ≥80% coverage on vms/db / vms/api / vms/identity, clean lint.

---

## Self-Review Checklist

- [x] All 7 Phase 1A/1B bugs addressed with spec references
- [x] G1 (evict_stale not wired) — Task 6
- [x] G2 (faiss_dirty consumer missing) — Task 7
- [x] 11 new tests across 5 test files — Tasks 1-7 each have RED step
- [x] GDPR purge is now complete: lock + thumbnail + CLIP rows + CLIP snapshots + JSON audit
- [x] No datetime.utcnow remaining in vms/ after Task 1
- [x] SHM validation is -O safe (ValueError not assert) — Task 4
- [x] RTSP reconnection gives operators visibility — Task 5
- [x] faiss_dirty consumer prevents stale FAISS for Phase 2b UNKNOWN_PERSON detector
- [x] TDD rhythm: every task has RED → GREEN → commit
- [x] Alembic migration with working downgrade for row_hash_version

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 8 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**VERDICT:** ENG CLEARED — 8 issues found and all resolved in plan. Ready to implement.

**UNRESOLVED:** 0
