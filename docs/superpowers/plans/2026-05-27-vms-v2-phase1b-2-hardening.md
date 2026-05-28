# Phase 1B.2 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [x]`) syntax for tracking.

**Status: COMPLETE** — 171 tests passing as of commit `210b283` (2026-05-28)

**Goal:** Close five Phase 1B correctness and reliability gaps: GDPR purge completeness,
SHM size validation, RTSP exponential backoff + camera deactivation, evict_stale wiring
in DBWriter, and faiss_dirty consumer startup replay.

**Architecture:** Touches ingestion worker, SHM slot, GDPR purge API route, identity
engine, and DB writer. No new modules. One config field added.

**Tech Stack:** SQLAlchemy 2.x, FastAPI, asyncio, fakeredis, pytest.

**Spec refs:**
- `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` §G (GDPR), §H (RTSP)
- `docs/superpowers/specs/2026-05-01-vms-db-edge-cases.md` §7 (GDPR cascade)
- CLAUDE.md §6.3 (idempotency), §6.5 (FAISS as derived cache)

---

## Task 3: GDPR purge completeness (T3)

- [x] 3.1 Replace `db.get(Person, ...)` with `SELECT ... FOR UPDATE` in `persons.py` purge route
- [x] 3.2 Add server-side bulk delete of `PersonClipEmbedding` via subquery join on `TrackingEvent`
- [x] 3.3 Collect `snapshot_path` values before delete; unlink files post-commit
- [x] 3.4 Unlink `thumbnail_path` file post-commit
- [x] 3.5 Store JSON audit payload `{"reason": ..., "embeddings_blanked": N}`
- [x] 3.6 Add 3 tests: `test_purge_audit_payload_is_json_with_required_keys`, `test_purge_person_deletes_thumbnail_file`, `test_purge_person_deletes_clip_embeddings`
- [x] 3.7 Commit: `fix: harden GDPR purge — SELECT FOR UPDATE, CLIP deletion, thumbnail unlink, JSON audit payload`

## Task 4: SHM size validation on open (T4)

- [x] 4.1 In `SHMSlot.open()`, compute expected size and raise `ValueError` on mismatch
- [x] 4.2 Add test `test_shm_slot_open_raises_value_error_on_size_mismatch`
- [x] 4.3 Commit: `fix: raise ValueError on SHM size mismatch in SHMSlot.open()`

## Task 5: RTSP exponential backoff + camera deactivation (T5)

- [x] 5.1 Add `_BACKOFF_DELAYS = (1, 2, 4, 8, 16, 32)` module constant in `worker.py`
- [x] 5.2 Add `rtsp_failure_threshold: int = 10` to `vms/config.py`
- [x] 5.3 Add `session_factory` parameter to `IngestionWorker.__init__`
- [x] 5.4 Add `_mark_camera_inactive()` coroutine
- [x] 5.5 Apply backoff delays and deactivate camera at threshold in `_capture_loop()`
- [x] 5.6 Add tests: `test_ingestion_worker_backoff_delays_increase_with_failures`, `test_ingestion_worker_marks_camera_inactive_after_failure_threshold`
- [x] 5.7 Commit: `fix: add RTSP exponential backoff and camera.is_active=False after failure threshold`

## Task 6: evict_stale wiring in DBWriter (T6)

- [x] 6.1 Verify `IdentityEngine.evict_stale()` already called every 1000 messages in `DBWriter.run()`
- [x] 6.2 No code change needed — already implemented in Phase 2a.1 identity framework

## Task 7: faiss_dirty consumer background task in DBWriter (T7)

- [x] 7.1 Add `STREAM = "faiss_dirty"` public constant to `vms/identity/faiss_dirty.py`
- [x] 7.2 Add `faiss_apply_add()` and `faiss_apply_remove()` to `IdentityEngine`
- [x] 7.3 Add `_consume_faiss_dirty()` coroutine to `DBWriter` (replays from `last_id="0"` on startup)
- [x] 7.4 Launch faiss consumer as `asyncio.create_task()` in `DBWriter.run()`
- [x] 7.5 Cancel task with `contextlib.suppress(asyncio.CancelledError)` in finally block
- [x] 7.6 Add 5 tests in `tests/test_identity_faiss_consumer.py`
- [x] 7.7 Commit: `feat: add faiss_dirty consumer background task in DBWriter with startup replay`
