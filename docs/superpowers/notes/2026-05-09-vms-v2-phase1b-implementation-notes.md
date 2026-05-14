# VMS v2 Phase 1B — Implementation Notes

**Phase:** 1B — Ingestion, Inference, and Base API
**Plan:** `docs/superpowers/plans/2026-05-09-vms-v2-phase1b-ingestion-inference-api.md`
**Branch:** `feat/phase-1b-ingestion-inference-api`

---

## Task 1: Redis Stream Client — COMPLETE

**Commit:** `40b6686`
**Files:** `vms/redis_client.py`, `tests/test_redis_client.py`

### Decisions

- `get_redis()` return type narrowed to `aioredis.Redis[str]` with `# type: ignore[return-value]` on the `from_url` call only — prevents `Any` propagating to all callers.
- `stream_read()` uses bare `XREAD` (no consumer group) — callers track their own `last_id`. `stream_ack()` requires the caller to have used `XREADGROUP` first; the API reflects this contract.
- `MAXLEN` defaults to `get_settings().redis_stream_maxlen` (500) so it is config-driven and never hard-coded.

### Fixes applied

- Weak ack test had no assertion — added `xreadgroup` + pending count check so the test catches a silent XACK failure.

---

## Task 2: SHM Slot + FramePointer — COMPLETE

**Commit:** `5c35613`
**Files:** `vms/ingestion/messages.py`, `vms/ingestion/shm.py`, `tests/test_ingestion_messages.py`, `tests/test_ingestion_shm.py`

### Decisions

- `HEADER_SIZE` and `HEADER_FMT` are **public** (no leading underscore) — tests import them as part of the SHM layout contract, not an implementation detail.
- Layout: 16-byte header (`seq_id: uint64 LE`, `timestamp_ms: uint64 LE`) followed by raw BGR bytes. This is fixed and must not change without a version bump.
- `FramePointer.to_redis_fields()` / `from_redis_fields()` encode all fields as strings — Redis Streams are string-typed.

### Fixes applied (critical)

- **`time.monotonic()` → `time.time_ns() // 1_000_000`**: `time.monotonic()` is process-relative. When the ingestion worker (writer) and inference engine (reader) run as separate OS processes, monotonic clocks are independent and stale checks would be wrong. Wall-clock `time_ns` is cross-process safe.
- Staleness test updated to mock `time.time_ns` instead of `time.monotonic`.

---

## Task 3: Ingestion Worker — COMPLETE

**Commit:** `d2f7969`
**Files:** `vms/ingestion/worker.py`, `tests/test_ingestion_worker.py`

### Decisions

- `CameraConfig` is a plain `@dataclass` (not frozen) — it is created once at startup and never mutated, but freezing it adds no safety benefit here.
- `_capture_loop` yields via `await asyncio.sleep(0)` after each publish so other coroutines get CPU time.
- On failed `cap.read()`: `logger.warning` + `await asyncio.sleep(0.1)` + `continue` — back-off without crashing.

### Fixes applied (critical)

- **`assert self._slot is not None` → `RuntimeError` guard**: Python strips `assert` statements when run with `-O` (optimised mode). The guard must be an explicit `RuntimeError` so it fires in production.

---

## Task 4: Inference DTOs — COMPLETE

**Commit:** `f87f6f8`
**Files:** `vms/inference/messages.py`, `tests/test_inference_messages.py`

### Decisions

- All three DTOs (`Tracklet`, `FaceWithEmbedding`, `DetectionFrame`) are `@dataclass(frozen=True)` — inter-process messages must be immutable.
- `FaceWithEmbedding.embedding` is `tuple[float, ...]` not `np.ndarray` — tuples are hashable, picklable, and safe to freeze. The embedder fills this in; an empty tuple `()` means "not yet embedded".
- `DetectionFrame.to_redis_fields()` JSON-serialises nested structs into two string keys (`tracklets`, `face_embeddings`). The schema is stable.

### Fixes applied

- Immutability test for `Tracklet` used bare `except Exception: pass` — swallowed real test failures. Replaced with `pytest.raises(FrozenInstanceError)`.

---

## Task 5: SCRFD Face Detector — COMPLETE

**Commit:** `0f7694a`
**Files:** `vms/inference/detector.py`, `tests/test_inference_detector.py`

### Decisions

- `SCRFDDetector.__init__` accepts a live `ort.InferenceSession` — enables mock injection for unit tests without loading an ONNX file.
- `from_path()` factory method is the production entry point; it handles provider selection (`CUDA → CPU` fallback).
- `import onnxruntime as ort` is **lazy** (inside `from_path()`) — `onnxruntime-gpu` had a broken `cuda_version` import at the time of development that crashed at module load. Lazy import keeps unit tests model-free.
- Output order assumed: `[cls_s8, cls_s16, cls_s32, bbox_s8, bbox_s16, bbox_s32]` — matches SCRFD 2.5g ONNX export convention. If a different SCRFD variant is used, verify output order matches.
- `np.meshgrid(..., indexing="ij")` — row-major indexing to match grid layout (height rows, width cols). Swapping to `"xy"` would silently produce wrong anchor coordinates.
- NMS via `cv2.dnn.NMSBoxes` — accepts `xywh` format; boxes are converted before call.

### Fixes applied

- Bare `import onnxruntime as ort` at module top level → moved inside `from_path()` (lazy import) to fix broken CUDA init crash in test environment.
- `_HEADER_SIZE`, `_HEADER_FMT` renamed from private to public in shm.py (carried over from Task 2 review).

---

## Task 6: AdaFace Embedder — COMPLETE

**Commit:** `5fbe727`
**Files:** `vms/inference/embedder.py`, `tests/test_inference_embedder.py`

### Decisions

- Lazy `import onnxruntime as ort` inside `from_path()` — same rationale as SCRFD detector (broken CUDA init at module load).
- `session: Any` constructor parameter to allow MagicMock injection in tests.
- Size check (`min_face_px`) runs BEFORE the numpy slice — required to satisfy `sess.run.assert_not_called()` in the skip test.
- Input name read from `session.get_inputs()[0].name` — not hardcoded.

### Fixes applied

- Removed unused `import pytest` (ruff F401).
- Removed redundant forward-reference quotes from `from_path` return type (ruff UP037, since `from __future__ import annotations` is active).

---

## Task 7: ByteTrack Tracker — COMPLETE

**Commit:** `54a1d0e`
**Files:** `vms/inference/tracker.py`, `tests/test_inference_tracker.py`

### Decisions

- `model: Any` constructor — allows MagicMock injection; lazy `from ultralytics import YOLO` inside `from_path()`.
- `zip(..., strict=False)` — ruff B905 requires explicit strictness on zip.
- `np.ndarray[Any, Any]` for `frame_bgr` — mypy needs explicit type args.
- `# type: ignore[attr-defined]` on YOLO import — ultralytics is typed but YOLO is not explicitly exported.

### Fixes applied

- Removed unused `Tracklet` import from test file.
- Added `strict=False` to `zip()` for ruff compliance.

---

## Task 8: Inference Engine — COMPLETE

**Commit:** `e41d885`
**Files:** `vms/inference/engine.py`, `tests/test_inference_engine.py`
**Also modified:** `vms/ingestion/shm.py`

### Decisions

- Engine calls `SHMSlot.open(name, width, height)` to attach to an existing shared memory segment — distinct from `SHMSlot.create()` which allocates. This required adding an `open()` classmethod to `shm.py` (the plan's constructor call `SHMSlot(name=..., width=..., height=...)` was invalid).
- `_running = False` flag set by the `fake_stream_add` side effect in tests — clean way to break the run loop for unit testing.
- Test patches target `vms.inference.engine.SHMSlot.open` (the classmethod).

### Fixes applied

- `SHMSlot.open()` classmethod added to `vms/ingestion/shm.py` to support attach-only semantics.
- Removed unused imports from test and engine (`asyncio`, `json`, `AsyncMock`, `FaceWithEmbedding`, `Tracklet`).

---

## Task 9: FastAPI App + Auth + Enrollment — COMPLETE

**Commit:** `f5f9d4f`
**Files:** `vms/api/` (6 files), `tests/test_api_health.py`, `tests/test_api_deps.py`, `tests/test_api_persons.py`

### Schema mismatches vs plan (real ORM wins)

- `Person` uses `name` not `full_name`; no `person_type` or `department` columns.
- `employee_id` is NOT NULL with unique constraint — enrollment requires it.
- `PersonEmbedding` has no `source` column; `EmbeddingCreate`/`EmbeddingResponse` exclude it.
- API schemas and tests were rewritten to match the actual ORM.

### Fixes applied

- `HTTPBearer(auto_error=False)` + manual 401 raise in `get_current_user` — FastAPI's default `auto_error=True` returns 403 on missing auth, but spec requires 401.
- `# noqa: B008` on all `Depends()` default params — ruff B008 false positive for FastAPI.
- `# type: ignore[import-untyped]` on `jose` import; cast `jwt.encode` return to `str`.
- `ASGITransport(app=app)` in tests — modern httpx (0.27+) requires this instead of `app=app` kwarg.

---

## Task 10: DB Writer — COMPLETE

**Commit:** `019e45e`
**Files:** `vms/writer/__init__.py`, `vms/writer/db_writer.py`, `tests/test_db_writer.py`

### Schema facts (real schema, not plan)

- `local_track_id` is `String(50)` — must cast `int` to `str` on insert.
- `global_track_id` UUID is required — generated fresh per row with `uuid.uuid4()`.
- `ingest_ts` (DateTime, NOT NULL) — set to `datetime.now(tz=timezone.utc)`.
- No `confidence` column — plan's test assertion was wrong.
- `event_ts` stored as `TIMESTAMP WITHOUT TIME ZONE` — timezone stripped with `.replace(tzinfo=None)`.
- FK to `cameras.camera_id` — integration tests create a `Camera` fixture first.

### Fixes applied

- Test file renamed from `test_writer_db_writer.py` to `test_db_writer.py` — original name sorts after `test_migration.py` (which runs `alembic downgrade base`), causing FK failures. New name sorts before migration test.
- Camera fixture added to tests to satisfy FK constraint.
- Test assertions updated to check `bbox_x1`, `bbox_x2`, `global_track_id` instead of non-existent `confidence`.

---

## Phase 1B final quality gates

| Check | Result |
|---|---|
| `pytest tests/ -q` | 96 passed |
| `ruff check vms/ tests/` | Clean |
| `black vms/ tests/` | Clean |
| `mypy vms/` | Clean (no errors) |
| `print()` in vms/ | None |
| Hard-coded thresholds | None — all use `get_settings()` |
| ONNX files committed | None |
| Phase status in CLAUDE.md | Updated to Phase 2 |

---

## Running state

| Task | Status | Commit | Tests |
|------|--------|--------|-------|
| Pre-flight | DONE | — | 57 baseline |
| Task 1: Redis Client | DONE | `40b6686` | +4 |
| Task 2: SHM + FramePointer | DONE | `5c35613` | +5 |
| Task 3: Ingestion Worker | DONE | `d2f7969` | +7 |
| Task 4: Inference DTOs | DONE | `f87f6f8` | +4 |
| Task 5: SCRFD Detector | DONE | `0f7694a` | +4 |
| **Total passing** | | | **77** |
| Task 6: AdaFace Embedder | DONE | `5fbe727` | +3 |
| Task 7: ByteTrack Tracker | DONE | `54a1d0e` | +3 |
| Task 8: Inference Engine | DONE | `e41d885` | +2 |
| Task 9: FastAPI App + Auth | DONE | `f5f9d4f` | +8 |
| Task 10: DB Writer | DONE | `019e45e` | +3 |
| **Final total** | | | **96** |
