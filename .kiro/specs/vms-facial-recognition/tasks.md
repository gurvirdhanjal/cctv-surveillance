# Implementation Plan — Phase 1: Foundation

> Scope: Wire the existing SCRFD + AdaFace + ByteTrack prototype into a production pipeline.
> webcam → shared memory → Redis Streams → GPU inference → MSSQL, with a basic FastAPI for enrollment and health.
> All tasks follow Red → Green → Commit TDD discipline.

## Tasks

- [ ] 1. Dependencies + Project Scaffold
  - [ ] 1.1 Update `requirements.txt` with pinned versions (fastapi, uvicorn, opencv-python-headless, ultralytics, numpy, onnxruntime-gpu, redis, sqlalchemy, pyodbc, alembic, pydantic-settings, python-jose, bcrypt, pytest, pytest-asyncio, httpx, faiss-cpu)
  - [ ] 1.2 Create `vms/__init__.py` (empty)
  - [ ] 1.3 Create `tests/conftest.py` with `env_vars` autouse fixture patching all required `VMS_*` environment variables
  - [ ] 1.4 Write failing test `tests/test_config.py` asserting `Settings` loads from env and default thresholds are correct
  - [ ] 1.5 Create `vms/config.py` with `Settings(BaseSettings)` using `VMS_` prefix, all inference thresholds, and a `get_settings()` singleton
  - [ ] 1.6 Run `pytest tests/test_config.py -v` and confirm PASS

- [ ] 2. Redis Client
  - [ ] 2.1 Write failing tests in `tests/test_redis_client.py` covering `xadd` field construction and `xreadgroup` message parsing
  - [ ] 2.2 Create `vms/redis_client.py` with `RedisClient` class implementing `xadd`, `xreadgroup`, `xack`, `ensure_group`, `hset`, `hgetall`, `ping`
  - [ ] 2.3 `xadd` MUST pass `maxlen` and `approximate=True` to Redis
  - [ ] 2.4 `xreadgroup` MUST decode byte keys/values and attach `_stream_id` to each message dict
  - [ ] 2.5 Run `pytest tests/test_redis_client.py -v` and confirm 2 PASS

- [ ] 3. SQLAlchemy Models
  - [ ] 3.1 Write failing tests in `tests/test_db_models.py` asserting all 11 tables are created and basic ORM round-trips work
  - [ ] 3.2 Create `vms/db/__init__.py` (empty)
  - [ ] 3.3 Create `vms/db/models.py` with all 11 ORM classes: `Person`, `PersonEmbedding`, `Camera`, `Zone`, `TrackingEvent`, `Alert`, `ReidMatch`, `ZonePresence`, `User`, `UserZonePermission`, `UserCameraPermission`
  - [ ] 3.4 `TrackingEvent` MUST have `UniqueConstraint("camera_id", "local_track_id", "event_ts")`
  - [ ] 3.5 Create `vms/db/session.py` with `get_engine()` and `get_session()` singletons; enable `fast_executemany` for MSSQL connections
  - [ ] 3.6 Run `pytest tests/test_db_models.py -v` and confirm 3 PASS

- [ ] 4. Alembic Migrations
  - [ ] 4.1 Run `alembic init alembic` to scaffold migration directory
  - [ ] 4.2 Replace `alembic/env.py` to import `Base.metadata` from `vms.db.models` and honour `VMS_DB_URL` env var override
  - [ ] 4.3 Run `alembic revision --autogenerate -m "initial_schema"` to generate the first migration
  - [ ] 4.4 Add explicit `op.create_index` calls to the generated migration for all indexes defined in the design doc (`idx_track_time`, `idx_track_person`, `idx_track_camera`, `idx_global_track`, `idx_zone_time`, `idx_person_pres`, `idx_alert_type`)
  - [ ] 4.5 Run `alembic upgrade head` against a local MSSQL instance and verify all 11 tables exist

- [ ] 5. Shared Memory Slot
  - [ ] 5.1 Write failing tests in `tests/test_shm.py` covering header size constant, write-then-read round-trip, and stale timestamp detection
  - [ ] 5.2 Create `vms/ingestion/__init__.py` (empty)
  - [ ] 5.3 Create `vms/ingestion/shm.py` with `SHMWriter` and `SHMReader`
  - [ ] 5.4 `SHMWriter.write()` MUST pack a 16-byte big-endian header `{seq_id: u64, timestamp_ms: u64}` before the raw BGR frame bytes
  - [ ] 5.5 `SHMReader.read()` MUST return `(seq_id, timestamp_ms, frame_bgr_ndarray)` as a copy
  - [ ] 5.6 `SHMReader.is_stale()` MUST return True when `now_ms - timestamp_ms > threshold_ms`
  - [ ] 5.7 Run `pytest tests/test_shm.py -v` and confirm 3 PASS

- [ ] 6. SCRFD Face Detector Wrapper
  - [ ] 6.1 Write failing tests in `tests/test_detector.py` covering `FaceDetection` dataclass, small-face filtering, and empty-frame list return
  - [ ] 6.2 Create `vms/inference/__init__.py` (empty)
  - [ ] 6.3 Create `vms/inference/detector.py` with `SCRFDDetector` class
  - [ ] 6.4 `SCRFDDetector.detect()` MUST preprocess to 640×640, run ONNX inference, decode multi-stride outputs, apply NMS, and filter faces smaller than `min_face_px`
  - [ ] 6.5 `SCRFDDetector` MUST default to `["CUDAExecutionProvider", "CPUExecutionProvider"]`
  - [ ] 6.6 Run `pytest tests/test_detector.py -v` and confirm 3 PASS

- [ ] 7. AdaFace Embedder Wrapper
  - [ ] 7.1 Write failing tests in `tests/test_embedder.py` covering embedding shape + L2 normalisation, blur rejection returning None, and empty crop returning None
  - [ ] 7.2 Create `vms/inference/embedder.py` with `AdaFaceEmbedder` class
  - [ ] 7.3 `AdaFaceEmbedder.embed()` MUST compute Laplacian variance and return `None` when below `min_blur`
  - [ ] 7.4 `AdaFaceEmbedder.embed()` MUST L2-normalise the raw ONNX output to unit norm (tolerance 1e-5)
  - [ ] 7.5 `AdaFaceEmbedder._preprocess()` MUST resize to 112×112, convert BGR→RGB, normalise to `(x - 127.5) / 128.0`
  - [ ] 7.6 Run `pytest tests/test_embedder.py -v` and confirm 3 PASS

- [ ] 8. Per-Camera ByteTrack Wrapper
  - [ ] 8.1 Write failing tests in `tests/test_tracker.py` covering track ID assignment, `Tracklet` dataclass, and empty-detection return
  - [ ] 8.2 Create `vms/inference/tracker.py` with `Tracklet` dataclass and `PerCameraTracker` class
  - [ ] 8.3 `PerCameraTracker` MUST load `BYTETracker` from `ultralytics.trackers.byte_tracker` using the YAML config
  - [ ] 8.4 `PerCameraTracker.update()` MUST accept `(N, 5)` detections array `[x1, y1, x2, y2, conf]` and return a list of `Tracklet` objects
  - [ ] 8.5 Each `Tracklet` MUST carry `local_track_id`, `cam_id`, `bbox`, `embedding`, `timestamp_ms`, `seq_id`
  - [ ] 8.6 Run `pytest tests/test_tracker.py -v` and confirm 3 PASS

- [ ] 9. Inference Engine
  - [ ] 9.1 Write failing tests in `tests/test_engine.py` covering end-to-end frame processing with mocked detector/embedder/tracker, empty-frame handling, and stale-frame skipping
  - [ ] 9.2 Create `vms/inference/engine.py` with `InferenceEngine` class
  - [ ] 9.3 `InferenceEngine` MUST read from the `frames:{group}` Redis_Stream via consumer group, attach to the SHM_Slot, validate staleness, run detector + embedder + tracker, and publish tracklets to the `detections` stream
  - [ ] 9.4 `InferenceEngine` MUST skip and XACK stale frames (age > `stale_threshold_ms`) and increment `frames_dropped` counter
  - [ ] 9.5 `InferenceEngine` MUST maintain one `PerCameraTracker` instance per `cam_id`
  - [ ] 9.6 Run `pytest tests/test_engine.py -v` and confirm all PASS

- [ ] 10. Ingestion Worker
  - [ ] 10.1 Write failing tests in `tests/test_ingestion_worker.py` covering frame write to SHM, Redis XADD call, and RTSP reconnect backoff logic
  - [ ] 10.2 Create `vms/ingestion/worker.py` with `IngestionWorker` class
  - [ ] 10.3 `IngestionWorker` MUST open the camera via `cv2.VideoCapture`, write each decoded frame to a `SHMWriter`, and publish `{cam_id, shm_name, seq_id, timestamp_ms}` to the appropriate `frames:{group}` stream
  - [ ] 10.4 `IngestionWorker` MUST register its SHM segment names in `shm_registry:{pid}` Redis hash on startup
  - [ ] 10.5 WHEN `cv2.VideoCapture.read()` fails, THE `IngestionWorker` SHALL apply exponential backoff (1→2→4→8→60s) before reconnecting
  - [ ] 10.6 Run `pytest tests/test_ingestion_worker.py -v` and confirm all PASS

- [ ] 11. DB Writer
  - [ ] 11.1 Write failing tests in `tests/test_db_writer.py` covering batch flush on row count, flush on timeout, and idempotent upsert behaviour
  - [ ] 11.2 Create `vms/writer/__init__.py` (empty)
  - [ ] 11.3 Create `vms/writer/db_writer.py` with `DBWriter` class
  - [ ] 11.4 `DBWriter` MUST read from the `tracking` Redis_Stream and accumulate rows in a buffer
  - [ ] 11.5 `DBWriter` MUST flush when buffer reaches 100 rows OR 500ms has elapsed since last flush
  - [ ] 11.6 `DBWriter` MUST use SQLAlchemy `executemany` bulk insert; on MSSQL use `MERGE` on `(camera_id, local_track_id, event_ts)` for idempotency
  - [ ] 11.7 WHEN a flush fails after 3 retries, THE `DBWriter` SHALL buffer rows in a circular in-memory deque (50k rows max) and write overflow to a local JSON file
  - [ ] 11.8 Run `pytest tests/test_db_writer.py -v` and confirm all PASS

- [ ] 12. FastAPI App + JWT Auth
  - [ ] 12.1 Write failing tests in `tests/test_api_health.py` covering `GET /api/health` response shape and unauthenticated access
  - [ ] 12.2 Create `vms/api/__init__.py`, `vms/api/main.py`, `vms/api/deps.py`, `vms/api/schemas.py`, `vms/api/routes/__init__.py`, `vms/api/routes/health.py`
  - [ ] 12.3 `vms/api/deps.py` MUST implement `get_db` (SQLAlchemy session dependency) and `get_current_user` (JWT decode + role extraction)
  - [ ] 12.4 `GET /api/health` MUST return `{status, redis_ok, db_ok, workers: [...]}` and be accessible without authentication
  - [ ] 12.5 WHEN a request carries an expired or invalid JWT, THE API_Server SHALL return HTTP 401
  - [ ] 12.6 Run `pytest tests/test_api_health.py -v` and confirm all PASS

- [ ] 13. Enrollment API
  - [ ] 13.1 Write failing tests in `tests/test_api_persons.py` covering `POST /api/persons`, `POST /api/persons/{id}/embeddings`, `GET /api/persons/search`, and duplicate employee_id rejection
  - [ ] 13.2 Create `vms/api/routes/persons.py` implementing the three enrollment endpoints
  - [ ] 13.3 `POST /api/persons` MUST create a `Person` row and return the new `person_id`
  - [ ] 13.4 `POST /api/persons/{id}/embeddings` MUST accept a face image, run `AdaFaceEmbedder.embed()`, and persist the result as a `PersonEmbedding` row
  - [ ] 13.5 WHEN `embed()` returns `None` (blurry or empty crop), THE endpoint SHALL return HTTP 422 with a descriptive message
  - [ ] 13.6 `GET /api/persons/search?q=` MUST query `persons.full_name` and `persons.employee_id` with a case-insensitive LIKE filter
  - [ ] 13.7 Run `pytest tests/test_api_persons.py -v` and confirm all PASS

- [ ] 14. Full Test Suite + Webcam Smoke Test
  - [ ] 14.1 Run `pytest tests/ -v` and confirm all tests pass with no errors
  - [ ] 14.2 Start all four processes manually (ingestion worker on webcam index 0, inference engine, DB writer, FastAPI) and verify the pipeline produces `tracking_events` rows in MSSQL within 30 seconds
  - [ ] 14.3 Enroll one person via `POST /api/persons` + `POST /api/persons/{id}/embeddings` (6 samples) and verify the person is recognised in subsequent frames
  - [ ] 14.4 Verify `GET /api/health` returns `redis_ok: true` and `db_ok: true`
