# VMS Phase 1 — Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing SCRFD + AdaFace + ByteTrack prototype into a production pipeline — webcam → shared memory → Redis Streams → GPU inference → MSSQL — with a basic FastAPI for enrollment and health checks.

**Architecture:** Four Python processes share a Redis Streams bus. Ingestion worker decodes webcam/RTSP frames into shared memory and publishes frame-pointer events. Inference engine (GPU) reads frame pointers, runs SCRFD + AdaFace + ByteTrack, and publishes confirmed tracklets. DB writer batches tracklets into MSSQL `tracking_events`. FastAPI serves enrollment and health. All processes are configured via a single `vms/config.py`.

**Tech Stack:** Python 3.11 · FastAPI 0.111 · SQLAlchemy 2.x + pyodbc (MSSQL Server) · Alembic · redis-py 5.x (Streams) · onnxruntime-gpu · ultralytics (ByteTracker) · pydantic-settings 2.x · python-jose (JWT) · bcrypt · pytest · pytest-asyncio

---

## File Map

```
vms/
├── __init__.py
├── config.py                        # All settings via pydantic-settings
├── redis_client.py                  # Redis connection + Stream helpers (XADD/XREAD/XACK)
├── db/
│   ├── __init__.py
│   ├── models.py                    # SQLAlchemy ORM — all 11 tables (complete schema)
│   └── session.py                   # engine + SessionLocal factory
├── ingestion/
│   ├── __init__.py
│   ├── shm.py                       # SHMSlot: write/read shared memory with header
│   └── worker.py                    # IngestionWorker: camera → shm → Redis Stream
├── inference/
│   ├── __init__.py
│   ├── detector.py                  # SCRFDDetector: SCRFD 2.5g ONNX wrapper
│   ├── embedder.py                  # AdaFaceEmbedder: AdaFace IR50 ONNX wrapper
│   ├── tracker.py                   # PerCameraTracker: ByteTrack wrapper per camera
│   └── engine.py                    # InferenceEngine: orchestrates detector+embedder+tracker
├── writer/
│   ├── __init__.py
│   └── db_writer.py                 # DBWriter: reads detections stream, batch-inserts to MSSQL
└── api/
    ├── __init__.py
    ├── main.py                      # FastAPI app, lifespan, router registration
    ├── deps.py                      # get_db, get_current_user (JWT)
    ├── schemas.py                   # Pydantic request/response models
    └── routes/
        ├── __init__.py
        ├── persons.py               # POST /api/persons, POST /api/persons/{id}/embeddings, GET /api/persons/search
        └── health.py                # GET /api/health

alembic.ini
alembic/
├── env.py
└── versions/
    └── 0001_initial_schema.py       # All 11 tables + indexes

tests/
├── conftest.py                      # Fixtures: in-memory SQLite engine, mock Redis, model paths
├── test_shm.py
├── test_detector.py
├── test_embedder.py
├── test_tracker.py
├── test_engine.py
├── test_db_models.py
├── test_api_persons.py
└── test_api_health.py
```

**Existing files reused (read-only):**
- `models/scrfd_2.5g.onnx` — face detector
- `models/adaface_ir50.onnx` — face embedder
- `bytetrack_custom.yaml` — tracker config
- `face_utils.py` — reference implementation (do not import; port patterns)

---

## Task 1: Dependencies + Project Scaffold

**Files:**
- Modify: `requirements.txt`
- Create: `vms/__init__.py`, `vms/config.py`

- [ ] **Step 1: Update requirements.txt**

Replace the contents of `requirements.txt`:

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
opencv-python-headless==4.9.0.80
ultralytics==8.2.0
numpy==1.26.4
onnxruntime-gpu==1.18.0
redis==5.0.4
sqlalchemy==2.0.30
pyodbc==5.1.0
alembic==1.13.1
pydantic-settings==2.2.1
python-jose[cryptography]==3.3.0
bcrypt==4.1.3
pytest==8.2.0
pytest-asyncio==0.23.6
httpx==0.27.0
faiss-cpu==1.8.0
```

- [ ] **Step 2: Install**

```bash
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 3: Create vms/__init__.py**

```python
```

(empty file)

- [ ] **Step 4: Write the failing config test**

Create `tests/conftest.py`:

```python
import os
import pytest
from unittest.mock import patch

@pytest.fixture(autouse=True)
def env_vars():
    with patch.dict(os.environ, {
        "VMS_DB_URL": "sqlite:///:memory:",
        "VMS_REDIS_URL": "redis://localhost:6379/0",
        "VMS_SCRFD_MODEL": "models/scrfd_2.5g.onnx",
        "VMS_ADAFACE_MODEL": "models/adaface_ir50.onnx",
        "VMS_JWT_SECRET": "test-secret-do-not-use",
        "VMS_BYTETRACK_CONFIG": "bytetrack_custom.yaml",
    }):
        yield
```

Create `tests/test_config.py`:

```python
from vms.config import Settings

def test_settings_load_from_env():
    s = Settings()
    assert s.db_url == "sqlite:///:memory:"
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.jwt_secret == "test-secret-do-not-use"
    assert s.adaface_min_sim == 0.72
    assert s.reid_cross_cam_sim == 0.65
```

- [ ] **Step 5: Run test — expect FAIL**

```bash
pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'vms.config'`

- [ ] **Step 6: Create vms/config.py**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VMS_", case_sensitive=False)

    db_url: str
    redis_url: str = "redis://localhost:6379/0"
    scrfd_model: str = "models/scrfd_2.5g.onnx"
    adaface_model: str = "models/adaface_ir50.onnx"
    bytetrack_config: str = "bytetrack_custom.yaml"
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 8

    # inference thresholds
    scrfd_conf: float = 0.60
    adaface_min_sim: float = 0.72
    reid_cross_cam_sim: float = 0.65
    reid_margin: float = 0.08
    min_blur: float = 25.0
    min_face_px: int = 40
    stale_threshold_ms: int = 200

    # pipeline tuning
    db_flush_rows: int = 100
    db_flush_ms: int = 500
    redis_stream_maxlen: int = 500


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

- [ ] **Step 7: Run test — expect PASS**

```bash
pytest tests/test_config.py -v
```

Expected: `PASSED`

- [ ] **Step 8: Commit**

```bash
git init  # if not already a repo
git add requirements.txt vms/__init__.py vms/config.py tests/conftest.py tests/test_config.py
git commit -m "feat: project scaffold and settings"
```

---

## Task 2: Redis Client

**Files:**
- Create: `vms/redis_client.py`
- Create: `tests/test_redis_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_redis_client.py
from unittest.mock import MagicMock, patch
import pytest
from vms.redis_client import RedisClient


def test_xadd_builds_correct_fields():
    mock_redis = MagicMock()
    client = RedisClient.__new__(RedisClient)
    client._r = mock_redis

    client.xadd("frames:groupA", {"cam_id": "1", "shm_name": "vms_cam_1", "seq_id": "42", "timestamp_ms": "1000"})

    mock_redis.xadd.assert_called_once_with(
        "frames:groupA",
        {"cam_id": "1", "shm_name": "vms_cam_1", "seq_id": "42", "timestamp_ms": "1000"},
        maxlen=500,
        approximate=True,
    )


def test_xread_returns_parsed_messages():
    mock_redis = MagicMock()
    client = RedisClient.__new__(RedisClient)
    client._r = mock_redis
    mock_redis.xreadgroup.return_value = [
        (b"frames:groupA", [(b"1-0", {b"cam_id": b"1", b"seq_id": b"5"})])
    ]

    msgs = client.xreadgroup("frames:groupA", "inference", "worker-1", count=10)

    assert len(msgs) == 1
    assert msgs[0]["cam_id"] == "1"
    assert msgs[0]["seq_id"] == "5"
    assert msgs[0]["_stream_id"] == "1-0"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_redis_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'vms.redis_client'`

- [ ] **Step 3: Create vms/redis_client.py**

```python
from __future__ import annotations

import redis
from vms.config import get_settings


class RedisClient:
    def __init__(self) -> None:
        s = get_settings()
        self._r = redis.from_url(s.redis_url, decode_responses=True)
        self._maxlen = s.redis_stream_maxlen

    def xadd(self, stream: str, fields: dict[str, str]) -> str:
        return self._r.xadd(stream, fields, maxlen=self._maxlen, approximate=True)

    def xreadgroup(
        self,
        stream: str,
        group: str,
        consumer: str,
        count: int = 50,
        block_ms: int = 100,
    ) -> list[dict]:
        raw = self._r.xreadgroup(
            group, consumer, {stream: ">"}, count=count, block=block_ms
        )
        if not raw:
            return []
        results = []
        for _stream, messages in raw:
            for msg_id, fields in messages:
                entry = {k: v for k, v in fields.items()}
                entry["_stream_id"] = msg_id
                results.append(entry)
        return results

    def xack(self, stream: str, group: str, *msg_ids: str) -> int:
        return self._r.xack(stream, group, *msg_ids)

    def ensure_group(self, stream: str, group: str) -> None:
        try:
            self._r.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.exceptions.ResponseError:
            pass  # group already exists

    def hset(self, key: str, mapping: dict[str, str]) -> None:
        self._r.hset(key, mapping=mapping)

    def hgetall(self, key: str) -> dict[str, str]:
        return self._r.hgetall(key)

    def ping(self) -> bool:
        return self._r.ping()
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_redis_client.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add vms/redis_client.py tests/test_redis_client.py
git commit -m "feat: redis client with stream helpers"
```

---

## Task 3: SQLAlchemy Models

**Files:**
- Create: `vms/db/__init__.py`, `vms/db/models.py`, `vms/db/session.py`
- Create: `tests/test_db_models.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_db_models.py
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from vms.db.models import Base, Person, PersonEmbedding, Camera, Zone, TrackingEvent, Alert, User


@pytest.fixture
def engine():
    e = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(e)
    return e


def test_all_tables_created(engine):
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    for name in ["persons", "person_embeddings", "cameras", "zones",
                 "tracking_events", "alerts", "reid_matches",
                 "zone_presence", "users",
                 "user_zone_permissions", "user_camera_permissions"]:
        assert name in tables, f"Missing table: {name}"


def test_person_roundtrip(engine):
    with Session(engine) as s:
        p = Person(full_name="Test User", person_type="employee", is_active=True)
        s.add(p)
        s.commit()
        s.refresh(p)
        assert p.person_id is not None
        assert p.full_name == "Test User"


def test_tracking_event_requires_camera(engine):
    with Session(engine) as s:
        cam = Camera(name="CAM-01", worker_group="A", is_active=True)
        s.add(cam)
        s.commit()
        evt = TrackingEvent(
            camera_id=cam.camera_id,
            local_track_id=1,
            bbox_x1=10, bbox_y1=10, bbox_x2=100, bbox_y2=100,
            confidence=0.95,
        )
        s.add(evt)
        s.commit()
        assert evt.event_id is not None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_db_models.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create vms/db/__init__.py**

```python
```

(empty)

- [ ] **Step 4: Create vms/db/models.py**

```python
from __future__ import annotations

import datetime
from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey,
    Integer, String, LargeBinary, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.dialects.mssql import UNIQUEIDENTIFIER
import uuid


class Base(DeclarativeBase):
    pass


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


class Person(Base):
    __tablename__ = "persons"

    person_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    person_type: Mapped[str] = mapped_column(String(20), default="unknown")
    thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    embeddings: Mapped[list[PersonEmbedding]] = relationship(back_populates="person")


class PersonEmbedding(Base):
    __tablename__ = "person_embeddings"

    embedding_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.person_id"), nullable=False, index=True)
    embedding: Mapped[bytes] = mapped_column(LargeBinary(2048), nullable=False)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="enrollment")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)

    person: Mapped[Person] = relationship(back_populates="embeddings")


class Camera(Base):
    __tablename__ = "cameras"

    camera_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rtsp_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    worker_group: Mapped[str] = mapped_column(String(1), default="A")
    homography_matrix: Mapped[str | None] = mapped_column(String, nullable=True)
    fov_polygon: Mapped[str | None] = mapped_column(String, nullable=True)
    resolution_w: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Zone(Base):
    __tablename__ = "zones"

    zone_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    polygon: Mapped[str | None] = mapped_column(String, nullable=True)
    max_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_restricted: Mapped[bool] = mapped_column(Boolean, default=False)
    adjacent_zone_ids: Mapped[str | None] = mapped_column(String, nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)


class TrackingEvent(Base):
    __tablename__ = "tracking_events"
    __table_args__ = (
        UniqueConstraint("camera_id", "local_track_id", "event_ts", name="uq_track_event"),
    )

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    global_track_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    person_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("persons.person_id"), nullable=True, index=True)
    camera_id: Mapped[int] = mapped_column(Integer, ForeignKey("cameras.camera_id"), nullable=False, index=True)
    zone_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("zones.zone_id"), nullable=True)
    local_track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_x1: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_y1: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_x2: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_y2: Mapped[int] = mapped_column(Integer, nullable=False)
    floor_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    floor_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_ts: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now, index=True, nullable=False)


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state: Mapped[str] = mapped_column(String(20), default="active", index=True)
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="HIGH")
    person_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("persons.person_id"), nullable=True)
    global_track_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    camera_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cameras.camera_id"), nullable=True)
    zone_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("zones.zone_id"), nullable=True)
    triggered_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    acknowledged_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.user_id"), nullable=True)
    snapshot_path: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ReidMatch(Base):
    __tablename__ = "reid_matches"

    match_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    global_track_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(Integer, ForeignKey("persons.person_id"), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    match_source: Mapped[str] = mapped_column(String(20), default="faiss")
    from_camera_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cameras.camera_id"), nullable=True)
    to_camera_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cameras.camera_id"), nullable=True)
    matched_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)


class ZonePresence(Base):
    __tablename__ = "zone_presence"

    presence_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    zone_id: Mapped[int] = mapped_column(Integer, ForeignKey("zones.zone_id"), nullable=False, index=True)
    global_track_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    person_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("persons.person_id"), nullable=True, index=True)
    entered_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=_now)
    exited_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="guard")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=_now)
    last_login: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)


class UserZonePermission(Base):
    __tablename__ = "user_zone_permissions"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id"), primary_key=True)
    zone_id: Mapped[int] = mapped_column(Integer, ForeignKey("zones.zone_id"), primary_key=True)


class UserCameraPermission(Base):
    __tablename__ = "user_camera_permissions"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id"), primary_key=True)
    camera_id: Mapped[int] = mapped_column(Integer, ForeignKey("cameras.camera_id"), primary_key=True)
```

- [ ] **Step 5: Create vms/db/session.py**

```python
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from vms.config import get_settings

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        s = get_settings()
        connect_args = {}
        if "mssql" in s.db_url:
            connect_args["fast_executemany"] = True
        _engine = create_engine(s.db_url, echo=False, connect_args=connect_args)
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal()
```

- [ ] **Step 6: Run tests — expect PASS**

```bash
pytest tests/test_db_models.py -v
```

Expected: `3 passed`

- [ ] **Step 7: Commit**

```bash
git add vms/db/ tests/test_db_models.py
git commit -m "feat: sqlalchemy models — all 11 tables"
```

---

## Task 4: Alembic Migrations (MSSQL)

**Files:**
- Create: `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_initial_schema.py`

- [ ] **Step 1: Initialise Alembic**

```bash
alembic init alembic
```

- [ ] **Step 2: Replace alembic/env.py**

```python
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from vms.db.models import Base

config = context.config

if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Allow VMS_DB_URL env var to override alembic.ini sqlalchemy.url
db_url = os.environ.get("VMS_DB_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Create first migration**

```bash
alembic revision --autogenerate -m "initial_schema"
```

Expected: creates `alembic/versions/xxxx_initial_schema.py`

- [ ] **Step 4: Add MSSQL indexes to the migration**

Open the generated migration file. Add after `op.create_table(...)` for `tracking_events`:

```python
op.create_index("idx_track_time",   "tracking_events", ["event_ts"], unique=False)
op.create_index("idx_track_person", "tracking_events", ["person_id", "event_ts"], unique=False)
op.create_index("idx_track_camera", "tracking_events", ["camera_id", "event_ts"], unique=False)
op.create_index("idx_global_track", "tracking_events", ["global_track_id"], unique=False)
op.create_index("idx_zone_time",    "zone_presence",   ["zone_id", "entered_at"], unique=False)
op.create_index("idx_person_pres",  "zone_presence",   ["person_id"], unique=False)
op.create_index("idx_alert_type",   "alerts",          ["alert_type", "triggered_at"], unique=False)
```

- [ ] **Step 5: Run migration against MSSQL**

```bash
# Set your MSSQL connection string
export VMS_DB_URL="mssql+pyodbc://sa:YourPassword@localhost/vms_dev?driver=ODBC+Driver+17+for+SQL+Server"
export VMS_JWT_SECRET="dev-secret"
alembic upgrade head
```

Expected: `Running upgrade  -> xxxx, initial_schema` — no errors.

- [ ] **Step 6: Verify tables exist**

```bash
python -c "
from sqlalchemy import create_engine, inspect
import os
e = create_engine(os.environ['VMS_DB_URL'])
print(inspect(e).get_table_names())
"
```

Expected: list of 11 table names printed.

- [ ] **Step 7: Commit**

```bash
git add alembic.ini alembic/
git commit -m "feat: alembic migrations — initial schema with indexes"
```

---

## Task 5: Shared Memory Slot

**Files:**
- Create: `vms/ingestion/__init__.py`, `vms/ingestion/shm.py`
- Create: `tests/test_shm.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_shm.py
import numpy as np
import struct
import time
import pytest
from vms.ingestion.shm import SHMWriter, SHMReader, SHM_HEADER_SIZE


def test_header_size_is_16():
    assert SHM_HEADER_SIZE == 16


def test_write_then_read_frame():
    width, height = 320, 240
    frame = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)

    writer = SHMWriter(cam_id=1, width=width, height=height)
    try:
        seq_id = writer.write(frame)
        assert seq_id == 1

        reader = SHMReader(writer.shm_name, width, height)
        seq, ts, recovered = reader.read()
        assert seq == 1
        assert abs(ts - int(time.time() * 1000)) < 2000
        np.testing.assert_array_equal(frame, recovered)
    finally:
        writer.close()


def test_stale_frame_detection():
    width, height = 64, 64
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    writer = SHMWriter(cam_id=2, width=width, height=height)
    try:
        writer.write(frame)
        reader = SHMReader(writer.shm_name, width, height)
        seq, ts, _ = reader.read()
        # manually age the timestamp
        stale_ts = ts - 5000  # 5 seconds ago
        assert stale_ts < ts
    finally:
        writer.close()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_shm.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create vms/ingestion/__init__.py**

```python
```

(empty)

- [ ] **Step 4: Create vms/ingestion/shm.py**

```python
from __future__ import annotations

import struct
import time
from multiprocessing import shared_memory

import numpy as np

SHM_HEADER_SIZE = 16  # seq_id (u64) + timestamp_ms (u64)
_HEADER_FMT = ">QQ"   # big-endian: uint64 seq_id, uint64 timestamp_ms


class SHMWriter:
    """Owns a shared memory segment for one camera. Writes frames with header."""

    def __init__(self, cam_id: int, width: int, height: int) -> None:
        self.cam_id = cam_id
        self.width = width
        self.height = height
        self._frame_bytes = width * height * 3
        self._total_bytes = SHM_HEADER_SIZE + self._frame_bytes
        self._seq: int = 0
        self._shm = shared_memory.SharedMemory(create=True, size=self._total_bytes)
        self.shm_name: str = self._shm.name

    def write(self, frame: np.ndarray) -> int:
        self._seq += 1
        ts_ms = int(time.time() * 1000)
        header = struct.pack(_HEADER_FMT, self._seq, ts_ms)
        self._shm.buf[:SHM_HEADER_SIZE] = header
        self._shm.buf[SHM_HEADER_SIZE : SHM_HEADER_SIZE + self._frame_bytes] = (
            frame.tobytes()
        )
        return self._seq

    def close(self) -> None:
        self._shm.close()
        self._shm.unlink()


class SHMReader:
    """Attaches to an existing shared memory segment to read frames."""

    def __init__(self, shm_name: str, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._frame_bytes = width * height * 3
        self._shm = shared_memory.SharedMemory(create=False, name=shm_name)

    def read(self) -> tuple[int, int, np.ndarray]:
        """Returns (seq_id, timestamp_ms, frame_bgr)."""
        header = bytes(self._shm.buf[:SHM_HEADER_SIZE])
        seq_id, timestamp_ms = struct.unpack(_HEADER_FMT, header)
        raw = bytes(self._shm.buf[SHM_HEADER_SIZE : SHM_HEADER_SIZE + self._frame_bytes])
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(self.height, self.width, 3).copy()
        return seq_id, timestamp_ms, frame

    def is_stale(self, timestamp_ms: int, threshold_ms: int = 200) -> bool:
        now_ms = int(time.time() * 1000)
        return (now_ms - timestamp_ms) > threshold_ms

    def close(self) -> None:
        self._shm.close()
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest tests/test_shm.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add vms/ingestion/ tests/test_shm.py
git commit -m "feat: shared memory slot with header validation"
```

---

## Task 6: SCRFD Face Detector Wrapper

**Files:**
- Create: `vms/inference/__init__.py`, `vms/inference/detector.py`
- Create: `tests/test_detector.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_detector.py
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from vms.inference.detector import SCRFDDetector, FaceDetection


def test_face_detection_dataclass():
    det = FaceDetection(bbox=(10, 20, 100, 120), confidence=0.85)
    assert det.bbox == (10, 20, 100, 120)
    assert det.confidence == 0.85


def test_detector_filters_small_faces():
    mock_sess = MagicMock()
    # SCRFD output: cls (N,1), bbox (N,4) for 3 strides × 2 arrays = 6 outputs
    # Simulate 1 detection at stride 8: high confidence but tiny bbox
    cls_out = np.array([[2.0]])   # pre-sigmoid → sigmoid ≈ 0.88
    bbox_out = np.array([[0.5, 0.5, 0.5, 0.5]])  # tiny box
    mock_sess.run.return_value = [cls_out, cls_out, cls_out, bbox_out, bbox_out, bbox_out]
    mock_sess.get_inputs.return_value = [MagicMock(name="input.1")]

    with patch("vms.inference.detector.ort.InferenceSession", return_value=mock_sess):
        det = SCRFDDetector("models/scrfd_2.5g.onnx", min_face_px=40)
        results = det.detect(np.zeros((480, 640, 3), dtype=np.uint8))
        # All faces below 40px should be filtered
        for r in results:
            w = r.bbox[2] - r.bbox[0]
            h = r.bbox[3] - r.bbox[1]
            assert w >= 40 and h >= 40


def test_detector_returns_list():
    mock_sess = MagicMock()
    mock_sess.run.return_value = [np.zeros((0, 1)), np.zeros((0, 1)), np.zeros((0, 1)),
                                   np.zeros((0, 4)), np.zeros((0, 4)), np.zeros((0, 4))]
    mock_sess.get_inputs.return_value = [MagicMock(name="input.1")]
    with patch("vms.inference.detector.ort.InferenceSession", return_value=mock_sess):
        det = SCRFDDetector("models/scrfd_2.5g.onnx")
        result = det.detect(np.zeros((480, 640, 3), dtype=np.uint8))
        assert isinstance(result, list)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_detector.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create vms/inference/__init__.py**

```python
```

(empty)

- [ ] **Step 4: Create vms/inference/detector.py**

```python
from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np
import onnxruntime as ort

from vms.config import get_settings


@dataclass
class FaceDetection:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float


_STRIDES = [8, 16, 32]
_ANCHORS_PER_CELL = 2


class SCRFDDetector:
    def __init__(
        self,
        model_path: str | None = None,
        conf_thres: float | None = None,
        min_face_px: int | None = None,
        providers: list[str] | None = None,
    ) -> None:
        s = get_settings()
        self._conf = conf_thres if conf_thres is not None else s.scrfd_conf
        self._min_px = min_face_px if min_face_px is not None else s.min_face_px
        path = model_path or s.scrfd_model
        _providers = providers or ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self._sess = ort.InferenceSession(path, providers=_providers)
        self._input_name: str = self._sess.get_inputs()[0].name

    def detect(self, frame_bgr: np.ndarray) -> list[FaceDetection]:
        h0, w0 = frame_bgr.shape[:2]
        inp = self._preprocess(frame_bgr)
        outputs = self._sess.run(None, {self._input_name: inp})
        return self._decode(outputs, h0, w0)

    def _preprocess(self, img: np.ndarray, size: int = 640) -> np.ndarray:
        resized = cv2.resize(img, (size, size))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
        normalized = (rgb - 127.5) / 128.0
        return np.transpose(normalized, (2, 0, 1))[None]

    def _decode(self, outputs: list[np.ndarray], h0: int, w0: int, input_size: int = 640) -> list[FaceDetection]:
        boxes_all, scores_all = [], []
        cls_outputs = outputs[0:3]
        bbox_outputs = outputs[3:6]

        for cls_out, bbox_out, stride in zip(cls_outputs, bbox_outputs, _STRIDES):
            if cls_out.shape[0] == 0:
                continue
            N = cls_out.shape[0]
            H = W = input_size // stride
            scores = 1.0 / (1.0 + np.exp(-cls_out[:, 0]))
            keep = scores > self._conf
            if not np.any(keep):
                continue
            scores = scores[keep]
            bbox = bbox_out[keep]
            HW = H * W
            anchors_per_cell = max(1, N // HW)
            ys, xs = np.meshgrid(np.arange(H), np.arange(W), indexing="ij")
            centers = np.stack([xs.ravel(), ys.ravel()], axis=1)
            centers = np.repeat(centers, anchors_per_cell, axis=0)[keep] * stride
            x1 = (centers[:, 0] - bbox[:, 0] * stride) * w0 / input_size
            y1 = (centers[:, 1] - bbox[:, 1] * stride) * h0 / input_size
            x2 = (centers[:, 0] + bbox[:, 2] * stride) * w0 / input_size
            y2 = (centers[:, 1] + bbox[:, 3] * stride) * h0 / input_size
            boxes_all.append(np.stack([x1, y1, x2, y2], axis=1))
            scores_all.append(scores)

        if not boxes_all:
            return []

        boxes = np.concatenate(boxes_all).astype(np.float32)
        scores = np.concatenate(scores_all).astype(np.float32)

        idxs = cv2.dnn.NMSBoxes(
            [[b[0], b[1], b[2] - b[0], b[3] - b[1]] for b in boxes],
            scores.tolist(), self._conf, 0.35,
        )
        if len(idxs) == 0:
            return []

        results = []
        for i in idxs.flatten():
            x1, y1, x2, y2 = map(int, boxes[i])
            if (x2 - x1) < self._min_px or (y2 - y1) < self._min_px:
                continue
            results.append(FaceDetection(bbox=(x1, y1, x2, y2), confidence=float(scores[i])))
        return results
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest tests/test_detector.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add vms/inference/__init__.py vms/inference/detector.py tests/test_detector.py
git commit -m "feat: SCRFD face detector wrapper"
```

---

## Task 7: AdaFace Embedder Wrapper

**Files:**
- Create: `vms/inference/embedder.py`
- Create: `tests/test_embedder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_embedder.py
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from vms.inference.embedder import AdaFaceEmbedder


def test_embedding_shape_and_normalized():
    mock_sess = MagicMock()
    raw_emb = np.random.randn(1, 512).astype(np.float32)
    raw_emb *= 5.0  # not normalized
    mock_sess.run.return_value = [raw_emb]
    mock_sess.get_inputs.return_value = [MagicMock(name="input")]

    with patch("vms.inference.embedder.ort.InferenceSession", return_value=mock_sess):
        emb = AdaFaceEmbedder("models/adaface_ir50.onnx")
        face = np.zeros((80, 60, 3), dtype=np.uint8)
        result = emb.embed(face)

    assert result.shape == (512,)
    assert abs(np.linalg.norm(result) - 1.0) < 1e-5


def test_blur_below_threshold_raises():
    with patch("vms.inference.embedder.ort.InferenceSession"):
        emb = AdaFaceEmbedder("models/adaface_ir50.onnx", min_blur=1000.0)
        solid_face = np.full((112, 112, 3), 128, dtype=np.uint8)
        result = emb.embed(solid_face)
        assert result is None


def test_embed_returns_none_on_empty_crop():
    with patch("vms.inference.embedder.ort.InferenceSession"):
        emb = AdaFaceEmbedder("models/adaface_ir50.onnx")
        result = emb.embed(np.zeros((0, 0, 3), dtype=np.uint8))
        assert result is None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_embedder.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create vms/inference/embedder.py**

```python
from __future__ import annotations

import cv2
import numpy as np
import onnxruntime as ort

from vms.config import get_settings


class AdaFaceEmbedder:
    """Produces L2-normalised 512-dim face embeddings via AdaFace IR50 ONNX."""

    def __init__(
        self,
        model_path: str | None = None,
        min_blur: float | None = None,
        providers: list[str] | None = None,
    ) -> None:
        s = get_settings()
        self._min_blur = min_blur if min_blur is not None else s.min_blur
        path = model_path or s.adaface_model
        _providers = providers or ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self._sess = ort.InferenceSession(path, providers=_providers)
        self._input_name: str = self._sess.get_inputs()[0].name

    def embed(self, face_bgr: np.ndarray) -> np.ndarray | None:
        if face_bgr is None or face_bgr.size == 0:
            return None
        if self._blur_score(face_bgr) < self._min_blur:
            return None
        inp = self._preprocess(face_bgr)
        raw = self._sess.run(None, {self._input_name: inp})[0][0].astype(np.float32)
        norm = np.linalg.norm(raw) + 1e-9
        return raw / norm

    @staticmethod
    def _blur_score(img: np.ndarray) -> float:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    @staticmethod
    def _preprocess(face: np.ndarray) -> np.ndarray:
        face = cv2.resize(face, (112, 112))
        face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB).astype(np.float32)
        face = (face - 127.5) / 128.0
        return np.transpose(face, (2, 0, 1))[None]
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_embedder.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add vms/inference/embedder.py tests/test_embedder.py
git commit -m "feat: adaface embedder with blur filter and L2 norm"
```

---

## Task 8: Per-Camera ByteTrack Wrapper

**Files:**
- Create: `vms/inference/tracker.py`
- Create: `tests/test_tracker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tracker.py
import numpy as np
import pytest
from vms.inference.tracker import PerCameraTracker, Tracklet


def _make_bboxes(n: int) -> np.ndarray:
    """Returns (n, 5) array of [x1, y1, x2, y2, conf]."""
    boxes = []
    for i in range(n):
        boxes.append([i * 50, 10, i * 50 + 40, 90, 0.9])
    return np.array(boxes, dtype=np.float32)


def test_tracker_assigns_track_ids():
    tracker = PerCameraTracker(cam_id=1, config_path="bytetrack_custom.yaml")
    bboxes = _make_bboxes(2)
    tracklets = tracker.update(bboxes, frame_shape=(480, 640))
    assert len(tracklets) == 2
    ids = [t.local_track_id for t in tracklets]
    assert len(set(ids)) == 2


def test_tracklet_dataclass():
    t = Tracklet(local_track_id=5, cam_id=1, bbox=(0, 0, 50, 50),
                 embedding=None, timestamp_ms=1000, seq_id=1)
    assert t.local_track_id == 5
    assert t.cam_id == 1


def test_tracker_returns_empty_on_no_detections():
    tracker = PerCameraTracker(cam_id=2, config_path="bytetrack_custom.yaml")
    result = tracker.update(np.zeros((0, 5), dtype=np.float32), frame_shape=(480, 640))
    assert result == []
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_tracker.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create vms/inference/tracker.py**

```python
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import yaml
from ultralytics.trackers.byte_tracker import BYTETracker
from ultralytics.utils import IterableSimpleNamespace


@dataclass
class Tracklet:
    local_track_id: int
    cam_id: int
    bbox: tuple[int, int, int, int]   # x1, y1, x2, y2
    embedding: np.ndarray | None
    timestamp_ms: int
    seq_id: int


class PerCameraTracker:
    """Wraps BYTETracker for one camera. Call update() each frame."""

    def __init__(self, cam_id: int, config_path: str = "bytetrack_custom.yaml") -> None:
        self.cam_id = cam_id
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        args = IterableSimpleNamespace(**cfg)
        self._tracker = BYTETracker(args, frame_rate=25)

    def update(
        self,
        detections: np.ndarray,            # (N, 5): [x1, y1, x2, y2, conf]
        frame_shape: tuple[int, int],      # (H, W)
        embeddings: list[np.ndarray | None] | None = None,
        seq_id: int = 0,
    ) -> list[Tracklet]:
        if detections.shape[0] == 0:
            return []

        tracks = self._tracker.update(detections, frame_shape, frame_shape)
        if tracks is None or len(tracks) == 0:
            return []

        ts_ms = int(time.time() * 1000)
        result: list[Tracklet] = []
        for track in tracks:
            tid = int(track.track_id)
            x1, y1, x2, y2 = map(int, track.tlbr)
            # Match embedding by detection index if provided
            emb = None
            if embeddings is not None and hasattr(track, "det_ind"):
                idx = track.det_ind
                if 0 <= idx < len(embeddings):
                    emb = embeddings[idx]
            result.append(Tracklet(
                local_track_id=tid,
                cam_id=self.cam_id,
                bbox=(x1, y1, x2, y2),
                embedding=emb,
                timestamp_ms=ts_ms,
                seq_id=seq_id,
            ))
        return result
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_tracker.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add vms/inference/tracker.py tests/test_tracker.py
git commit -m "feat: per-camera bytetrack wrapper"
```

---

## Task 9: Inference Engine

**Files:**
- Create: `vms/inference/engine.py`
- Create: `tests/test_engine.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_engine.py
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from vms.inference.engine import InferenceEngine
from vms.inference.detector import FaceDetection
from vms.inference.tracker import Tracklet


def _make_engine():
    mock_detector = MagicMock()
    mock_embedder = MagicMock()
    mock_tracker = MagicMock()

    eng = InferenceEngine.__new__(InferenceEngine)
    eng._detector = mock_detector
    eng._embedder = mock_embedder
    eng._trackers = {1: mock_tracker}
    from vms.config import get_settings
    eng._settings = get_settings()
    return eng, mock_detector, mock_embedder, mock_tracker


def test_process_frame_returns_tracklets():
    eng, det, emb, tracker = _make_engine()
    det.detect.return_value = [FaceDetection(bbox=(10, 10, 80, 80), confidence=0.9)]
    emb.embed.return_value = np.ones(512, dtype=np.float32) / np.sqrt(512)
    tracker.update.return_value = [
        Tracklet(local_track_id=1, cam_id=1, bbox=(10, 10, 80, 80),
                 embedding=None, timestamp_ms=1000, seq_id=1)
    ]

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracklets = eng.process_frame(cam_id=1, frame=frame, seq_id=1)

    assert len(tracklets) == 1
    assert tracklets[0].local_track_id == 1
    assert tracklets[0].embedding is not None


def test_process_frame_skips_no_faces():
    eng, det, emb, tracker = _make_engine()
    det.detect.return_value = []
    tracker.update.return_value = []

    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracklets = eng.process_frame(cam_id=1, frame=frame, seq_id=1)
    assert tracklets == []


def test_engine_creates_tracker_for_new_camera():
    eng, det, emb, _ = _make_engine()
    eng._trackers = {}
    det.detect.return_value = []

    with patch("vms.inference.engine.PerCameraTracker") as MockTracker:
        MockTracker.return_value.update.return_value = []
        eng.process_frame(cam_id=99, frame=np.zeros((480, 640, 3), dtype=np.uint8), seq_id=1)
        assert 99 in eng._trackers
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_engine.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create vms/inference/engine.py**

```python
from __future__ import annotations

import numpy as np

from vms.config import Settings, get_settings
from vms.inference.detector import SCRFDDetector, FaceDetection
from vms.inference.embedder import AdaFaceEmbedder
from vms.inference.tracker import PerCameraTracker, Tracklet


class InferenceEngine:
    """Orchestrates detector + embedder + per-camera ByteTrack.

    One instance per GPU process. Call process_frame() for each decoded frame.
    """

    def __init__(self, bytetrack_config: str | None = None) -> None:
        self._settings: Settings = get_settings()
        self._detector = SCRFDDetector()
        self._embedder = AdaFaceEmbedder()
        self._bt_config = bytetrack_config or self._settings.bytetrack_config
        self._trackers: dict[int, PerCameraTracker] = {}

    def process_frame(
        self,
        cam_id: int,
        frame: np.ndarray,
        seq_id: int,
    ) -> list[Tracklet]:
        if cam_id not in self._trackers:
            self._trackers[cam_id] = PerCameraTracker(cam_id=cam_id, config_path=self._bt_config)

        detections: list[FaceDetection] = self._detector.detect(frame)
        if not detections:
            self._trackers[cam_id].update(
                np.zeros((0, 5), dtype=np.float32),
                frame_shape=frame.shape[:2],
                seq_id=seq_id,
            )
            return []

        # Compute embeddings for each detected face
        embeddings: list[np.ndarray | None] = []
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            crop = frame[y1:y2, x1:x2]
            embeddings.append(self._embedder.embed(crop))

        # Feed detections to ByteTrack
        bbox_array = np.array(
            [[*d.bbox, d.confidence] for d in detections], dtype=np.float32
        )
        tracklets = self._trackers[cam_id].update(
            bbox_array,
            frame_shape=frame.shape[:2],
            embeddings=embeddings,
            seq_id=seq_id,
        )

        # Attach embeddings to tracklets by matching bboxes
        for tracklet in tracklets:
            if tracklet.embedding is None:
                tx1, ty1, tx2, ty2 = tracklet.bbox
                for det, emb in zip(detections, embeddings):
                    dx1, dy1, dx2, dy2 = det.bbox
                    if abs(tx1 - dx1) < 10 and abs(ty1 - dy1) < 10:
                        tracklet.embedding = emb
                        break

        return tracklets
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_engine.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add vms/inference/engine.py tests/test_engine.py
git commit -m "feat: inference engine orchestrating scrfd+adaface+bytetrack"
```

---

## Task 10: Ingestion Worker

**Files:**
- Create: `vms/ingestion/worker.py`
- Create: `tests/test_ingestion_worker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ingestion_worker.py
import numpy as np
import pytest
from unittest.mock import MagicMock, patch, call
from vms.ingestion.worker import IngestionWorker


def _make_worker(cam_id: int = 1, source: int | str = 0) -> IngestionWorker:
    worker = IngestionWorker.__new__(IngestionWorker)
    worker.cam_id = cam_id
    worker.source = source
    worker._running = False
    return worker


def test_worker_publishes_frame_ref_to_redis():
    mock_redis = MagicMock()
    mock_cap = MagicMock()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Return one frame then stop
    mock_cap.read.side_effect = [(True, frame), (False, None)]
    mock_cap.get.return_value = 640.0

    mock_shm_writer = MagicMock()
    mock_shm_writer.shm_name = "vms_cam_1"
    mock_shm_writer.write.return_value = 1

    with patch("vms.ingestion.worker.cv2.VideoCapture", return_value=mock_cap), \
         patch("vms.ingestion.worker.SHMWriter", return_value=mock_shm_writer):
        worker = IngestionWorker(cam_id=1, source=0, redis_client=mock_redis, worker_group="A")
        worker._run_once()

    mock_redis.xadd.assert_called_once()
    call_args = mock_redis.xadd.call_args
    assert call_args[0][0] == "frames:groupA"
    fields = call_args[0][1]
    assert fields["cam_id"] == "1"
    assert fields["shm_name"] == "vms_cam_1"
    assert fields["seq_id"] == "1"


def test_worker_registers_heartbeat():
    mock_redis = MagicMock()
    worker = IngestionWorker.__new__(IngestionWorker)
    worker.cam_id = 1
    worker._redis = mock_redis
    worker._worker_id = "worker-A"

    worker._refresh_heartbeat()

    mock_redis.hset.assert_called_once()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_ingestion_worker.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create vms/ingestion/worker.py**

```python
from __future__ import annotations

import os
import time
import signal
import logging

import cv2
import numpy as np

from vms.config import get_settings
from vms.ingestion.shm import SHMWriter
from vms.redis_client import RedisClient

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL_S = 10
_HEARTBEAT_TTL_S = 15


class IngestionWorker:
    """Reads frames from one camera, writes to shared memory, publishes ref to Redis Stream."""

    def __init__(
        self,
        cam_id: int,
        source: int | str,
        redis_client: RedisClient,
        worker_group: str = "A",
        width: int = 640,
        height: int = 480,
    ) -> None:
        self.cam_id = cam_id
        self.source = source
        self._redis = redis_client
        self._group = worker_group
        self._stream = f"frames:group{worker_group}"
        self._worker_id = f"ingestion-{worker_group}-{os.getpid()}"
        self._width = width
        self._height = height
        self._settings = get_settings()
        self._shm_writer: SHMWriter | None = None
        self._running = False

    def _run_once(self) -> bool:
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            logger.error("Cannot open source %s", self.source)
            return False

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or self._width
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or self._height

        self._shm_writer = SHMWriter(cam_id=self.cam_id, width=actual_w, height=actual_h)
        # Register SHM name so supervisor can clean up on crash
        self._redis.hset(f"shm_registry:{os.getpid()}", {self._shm_writer.shm_name: "1"})

        ok, frame = cap.read()
        if not ok:
            cap.release()
            return False

        seq_id = self._shm_writer.write(frame)
        ts_ms = int(time.time() * 1000)

        self._redis.xadd(self._stream, {
            "cam_id": str(self.cam_id),
            "shm_name": self._shm_writer.shm_name,
            "seq_id": str(seq_id),
            "timestamp_ms": str(ts_ms),
            "width": str(actual_w),
            "height": str(actual_h),
            "schema_version": "1",
        })
        cap.release()
        return True

    def _refresh_heartbeat(self) -> None:
        self._redis.hset(f"heartbeat:{self._worker_id}", {
            "worker_id": self._worker_id,
            "cam_id": str(self.cam_id),
            "ts": str(int(time.time())),
        })

    def run(self) -> None:
        s = self._settings
        self._running = True
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open source {self.source}")

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or self._width
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or self._height
        self._shm_writer = SHMWriter(cam_id=self.cam_id, width=actual_w, height=actual_h)
        self._redis.hset(f"shm_registry:{os.getpid()}", {self._shm_writer.shm_name: "1"})

        last_heartbeat = 0.0

        try:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    logger.warning("cam_id=%d: read failed, retrying...", self.cam_id)
                    time.sleep(1.0)
                    cap.release()
                    cap = cv2.VideoCapture(self.source)
                    continue

                seq_id = self._shm_writer.write(frame)
                ts_ms = int(time.time() * 1000)

                self._redis.xadd(self._stream, {
                    "cam_id": str(self.cam_id),
                    "shm_name": self._shm_writer.shm_name,
                    "seq_id": str(seq_id),
                    "timestamp_ms": str(ts_ms),
                    "width": str(actual_w),
                    "height": str(actual_h),
                    "schema_version": "1",
                })

                now = time.time()
                if now - last_heartbeat >= _HEARTBEAT_INTERVAL_S:
                    self._refresh_heartbeat()
                    last_heartbeat = now

        finally:
            cap.release()
            if self._shm_writer:
                self._shm_writer.close()

    def stop(self) -> None:
        self._running = False
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_ingestion_worker.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add vms/ingestion/worker.py tests/test_ingestion_worker.py
git commit -m "feat: ingestion worker — rtsp/webcam to shared memory + redis streams"
```

---

## Task 11: DB Writer (Batch Insert)

**Files:**
- Create: `vms/writer/__init__.py`, `vms/writer/db_writer.py`
- Create: `tests/test_db_writer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_db_writer.py
import datetime
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from vms.db.models import Base, TrackingEvent, Camera
from vms.writer.db_writer import DBWriter, TrackletRow


@pytest.fixture
def mem_engine():
    e = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(e)
    with Session(e) as s:
        cam = Camera(name="CAM-01", worker_group="A", is_active=True)
        s.add(cam)
        s.commit()
    return e


def test_flush_inserts_rows(mem_engine):
    writer = DBWriter.__new__(DBWriter)
    writer._engine = mem_engine
    writer._buffer = [
        TrackletRow(camera_id=1, local_track_id=1,
                    bbox_x1=10, bbox_y1=10, bbox_x2=80, bbox_y2=80,
                    confidence=0.9, event_ts=datetime.datetime.utcnow()),
        TrackletRow(camera_id=1, local_track_id=2,
                    bbox_x1=50, bbox_y1=50, bbox_x2=120, bbox_y2=120,
                    confidence=0.85, event_ts=datetime.datetime.utcnow()),
    ]
    writer._flush()
    with Session(mem_engine) as s:
        count = s.query(TrackingEvent).count()
    assert count == 2


def test_flush_clears_buffer(mem_engine):
    writer = DBWriter.__new__(DBWriter)
    writer._engine = mem_engine
    writer._buffer = []
    writer._flush()  # should not raise
    assert writer._buffer == []
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_db_writer.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create vms/writer/__init__.py**

```python
```

(empty)

- [ ] **Step 4: Create vms/writer/db_writer.py**

```python
from __future__ import annotations

import datetime
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from vms.config import get_settings
from vms.db.models import TrackingEvent

logger = logging.getLogger(__name__)


@dataclass
class TrackletRow:
    camera_id: int
    local_track_id: int
    bbox_x1: int
    bbox_y1: int
    bbox_x2: int
    bbox_y2: int
    confidence: float
    event_ts: datetime.datetime
    global_track_id: str | None = None
    person_id: int | None = None
    floor_x: float | None = None
    floor_y: float | None = None


class DBWriter:
    """Buffers TrackletRow objects and batch-inserts them into tracking_events."""

    def __init__(self) -> None:
        s = get_settings()
        self._engine: Engine = create_engine(s.db_url, echo=False)
        self._buffer: list[TrackletRow] = []
        self._flush_rows = s.db_flush_rows
        self._flush_ms = s.db_flush_ms
        self._last_flush = time.monotonic()

    def add(self, row: TrackletRow) -> None:
        self._buffer.append(row)
        now = time.monotonic()
        if (len(self._buffer) >= self._flush_rows or
                (now - self._last_flush) * 1000 >= self._flush_ms):
            self._flush()

    def _flush(self) -> None:
        if not self._buffer:
            return
        rows = self._buffer[:]
        self._buffer.clear()
        self._last_flush = time.monotonic()
        try:
            with Session(self._engine) as session:
                session.bulk_insert_mappings(TrackingEvent, [
                    {
                        "global_track_id": r.global_track_id,
                        "person_id": r.person_id,
                        "camera_id": r.camera_id,
                        "local_track_id": r.local_track_id,
                        "bbox_x1": r.bbox_x1,
                        "bbox_y1": r.bbox_y1,
                        "bbox_x2": r.bbox_x2,
                        "bbox_y2": r.bbox_y2,
                        "floor_x": r.floor_x,
                        "floor_y": r.floor_y,
                        "confidence": r.confidence,
                        "event_ts": r.event_ts,
                    }
                    for r in rows
                ])
                session.commit()
        except Exception:
            logger.exception("DB flush failed — %d rows dropped", len(rows))
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest tests/test_db_writer.py -v
```

Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add vms/writer/ tests/test_db_writer.py
git commit -m "feat: db writer with batch insert and flush strategy"
```

---

## Task 12: FastAPI App + JWT Auth

**Files:**
- Create: `vms/api/__init__.py`, `vms/api/main.py`, `vms/api/deps.py`, `vms/api/schemas.py`
- Create: `vms/api/routes/__init__.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_api_health.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def client():
    with patch("vms.api.deps.get_session", return_value=MagicMock()):
        from vms.api.main import app
        return TestClient(app)


def test_health_returns_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_unknown_route_returns_404(client):
    resp = client.get("/api/nonexistent")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_api_health.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create vms/api/__init__.py and routes/__init__.py**

Both empty files.

- [ ] **Step 4: Create vms/api/schemas.py**

```python
from __future__ import annotations

import datetime
from pydantic import BaseModel, EmailStr


class PersonCreate(BaseModel):
    full_name: str
    employee_id: str | None = None
    department: str | None = None
    person_type: str = "employee"


class PersonOut(BaseModel):
    person_id: int
    full_name: str | None
    employee_id: str | None
    department: str | None
    person_type: str
    is_active: bool
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class PersonSearchResult(BaseModel):
    person_id: int
    full_name: str | None
    employee_id: str | None
    person_type: str

    model_config = {"from_attributes": True}


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime.datetime
```

- [ ] **Step 5: Create vms/api/deps.py**

```python
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from vms.config import get_settings
from vms.db.session import get_session
from vms.db.models import User

_bearer = HTTPBearer()


def get_db() -> Session:
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    s = get_settings()
    try:
        payload = jwt.decode(credentials.credentials, s.jwt_secret, algorithms=[s.jwt_algorithm])
        user_id: int | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(User).filter(User.user_id == int(user_id), User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_role(*roles: str):
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return current_user
    return checker
```

- [ ] **Step 6: Create vms/api/routes/health.py**

```python
import datetime
from fastapi import APIRouter
from vms.api.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.datetime.utcnow())
```

- [ ] **Step 7: Create vms/api/main.py**

```python
from fastapi import FastAPI
from vms.api.routes import health, persons

app = FastAPI(title="VMS API", version="0.1.0")

app.include_router(health.router)
app.include_router(persons.router)
```

- [ ] **Step 8: Create vms/api/routes/persons.py (stub)**

```python
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from vms.api.deps import get_db, get_current_user, require_role
from vms.api.schemas import PersonCreate, PersonOut, PersonSearchResult
from vms.db.models import Person

router = APIRouter(prefix="/api/persons", tags=["persons"])


@router.get("/search", response_model=list[PersonSearchResult])
def search_persons(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    _: Person = Depends(require_role("guard", "manager", "admin")),
) -> list[PersonSearchResult]:
    results = db.query(Person).filter(
        (Person.full_name.ilike(f"%{q}%")) | (Person.employee_id.ilike(f"%{q}%"))
    ).limit(20).all()
    return results


@router.post("", response_model=PersonOut, status_code=201)
def create_person(
    body: PersonCreate,
    db: Session = Depends(get_db),
    _: Person = Depends(require_role("admin")),
) -> PersonOut:
    person = Person(**body.model_dump())
    db.add(person)
    db.commit()
    db.refresh(person)
    return person
```

- [ ] **Step 9: Run — expect PASS**

```bash
pytest tests/test_api_health.py -v
```

Expected: `2 passed`

- [ ] **Step 10: Commit**

```bash
git add vms/api/ tests/test_api_health.py
git commit -m "feat: fastapi app with JWT auth, health endpoint, person search"
```

---

## Task 13: Enrollment API

**Files:**
- Modify: `vms/api/routes/persons.py`
- Create: `tests/test_api_persons.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_api_persons.py
import io
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from unittest.mock import patch, MagicMock
from vms.db.models import Base, Camera


@pytest.fixture
def app_client():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    def override_db():
        with Session(engine) as s:
            yield s

    from vms.api.main import app
    from vms.api.deps import get_db
    app.dependency_overrides[get_db] = override_db

    with patch("vms.api.deps.get_current_user", return_value=MagicMock(role="admin")):
        yield TestClient(app)

    app.dependency_overrides.clear()


def test_create_person(app_client):
    resp = app_client.post("/api/persons", json={
        "full_name": "Test Employee",
        "employee_id": "EMP-001",
        "department": "Engineering",
        "person_type": "employee",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["person_id"] is not None
    assert data["full_name"] == "Test Employee"
    assert data["employee_id"] == "EMP-001"


def test_search_persons_returns_match(app_client):
    app_client.post("/api/persons", json={
        "full_name": "Gurvir Singh",
        "employee_id": "EMP-042",
        "person_type": "employee",
    })
    resp = app_client.get("/api/persons/search?q=gurvir")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert any(r["full_name"] == "Gurvir Singh" for r in results)


def test_add_embedding_to_person(app_client):
    create_resp = app_client.post("/api/persons", json={
        "full_name": "Face Test",
        "person_type": "employee",
    })
    person_id = create_resp.json()["person_id"]

    # 512 float32 embeddings serialized as bytes
    emb = np.random.randn(512).astype(np.float32)
    emb = emb / np.linalg.norm(emb)
    emb_bytes = emb.tobytes()

    resp = app_client.post(
        f"/api/persons/{person_id}/embeddings",
        content=emb_bytes,
        headers={"Content-Type": "application/octet-stream", "X-Quality-Score": "45.2"},
    )
    assert resp.status_code == 201
    assert resp.json()["embedding_id"] is not None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_api_persons.py -v
```

Expected: `test_add_embedding_to_person` fails — endpoint missing.

- [ ] **Step 3: Add EmbeddingOut to vms/api/schemas.py**

Add after the existing `TokenResponse` class in `vms/api/schemas.py`:

```python
class EmbeddingOut(BaseModel):
    embedding_id: int
    person_id: int
    quality_score: float | None
    source: str

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Add embedding endpoint to vms/api/routes/persons.py**

Add after the existing `create_person` route (do not re-add existing imports — they are already at the top of the file from Task 12):

```python
from fastapi import Request
from vms.api.schemas import EmbeddingOut
from vms.db.models import PersonEmbedding


@router.post("/{person_id}/embeddings", response_model=EmbeddingOut, status_code=201)
async def add_embedding(
    person_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(require_role("admin")),
) -> EmbeddingOut:
    person = db.query(Person).filter(Person.person_id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    raw = await request.body()
    if len(raw) != 512 * 4:
        raise HTTPException(status_code=422, detail="Embedding must be 512 float32 values (2048 bytes)")

    quality = float(request.headers.get("X-Quality-Score", "0"))
    emb = PersonEmbedding(
        person_id=person_id,
        embedding=raw,
        quality_score=quality,
        source="enrollment",
    )
    db.add(emb)
    db.commit()
    db.refresh(emb)
    return emb
```

- [ ] **Step 5: Run — expect PASS**

```bash
pytest tests/test_api_persons.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add vms/api/routes/persons.py vms/api/schemas.py tests/test_api_persons.py
git commit -m "feat: enrollment API — create person and add embeddings"
```

---

## Task 14: Run Full Test Suite + Webcam Smoke Test

**Files:**
- No new files

- [ ] **Step 1: Run all unit tests**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests pass. If any fail, fix before proceeding.

- [ ] **Step 2: Start Redis locally**

```bash
# Windows — Redis via WSL or Docker
docker run -d --name redis-vms -p 6379:6379 redis:7-alpine
```

- [ ] **Step 3: Set environment variables**

```bash
export VMS_DB_URL="mssql+pyodbc://sa:YourPassword@localhost/vms_dev?driver=ODBC+Driver+17+for+SQL+Server"
export VMS_REDIS_URL="redis://localhost:6379/0"
export VMS_JWT_SECRET="dev-secret-change-in-prod"
export VMS_SCRFD_MODEL="models/scrfd_2.5g.onnx"
export VMS_ADAFACE_MODEL="models/adaface_ir50.onnx"
```

- [ ] **Step 4: Create the webcam smoke test script**

Create `scripts/smoke_test_webcam.py`:

```python
"""Smoke test: ingestion + inference on webcam, print tracklets to console."""
import os
import sys
import time
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from vms.inference.engine import InferenceEngine

engine = InferenceEngine()
cap = cv2.VideoCapture(0)

print("[smoke] Press Q to quit")
frame_idx = 0

while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame_idx += 1
    if frame_idx % 3 != 0:  # process every 3rd frame
        continue

    tracklets = engine.process_frame(cam_id=1, frame=frame, seq_id=frame_idx)

    for t in tracklets:
        x1, y1, x2, y2 = t.bbox
        has_emb = t.embedding is not None
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(frame, f"T{t.local_track_id} {'[emb]' if has_emb else ''}", 
                    (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 1)

    cv2.imshow("Smoke Test — VMS Phase 1", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
print(f"[smoke] Processed {frame_idx} frames. Inference engine OK.")
```

- [ ] **Step 5: Run the smoke test**

```bash
python scripts/smoke_test_webcam.py
```

Expected: window opens, faces detected and labelled with track IDs, embeddings computed (`[emb]` shown when embedding is non-null). Press Q to quit.

- [ ] **Step 6: Start FastAPI and verify health endpoint**

```bash
uvicorn vms.api.main:app --reload --port 8000
```

In another terminal:
```bash
curl http://localhost:8000/api/health
```

Expected:
```json
{"status": "ok", "timestamp": "2026-04-23T..."}
```

- [ ] **Step 7: Final commit**

```bash
git add scripts/smoke_test_webcam.py
git commit -m "chore: add webcam smoke test for phase 1 validation"
```

---

## Phase 1 Complete — What Was Built

| Component | Status |
|---|---|
| SQLAlchemy models (all 11 tables) | ✅ |
| Alembic migrations + indexes | ✅ |
| Shared memory with header safety | ✅ |
| SCRFD face detector wrapper | ✅ |
| AdaFace embedder with blur filter | ✅ |
| ByteTrack per-camera wrapper | ✅ |
| Inference engine (full pipeline) | ✅ |
| Ingestion worker (webcam → Redis Streams) | ✅ |
| DB writer (batch insert) | ✅ |
| FastAPI + JWT auth + health endpoint | ✅ |
| Person enrollment API | ✅ |

## What's Next — Phase 2

Phase 2 plan covers:
- FAISS flat IP index + zone-adjacency pre-filter
- Cross-camera Re-ID service reading the `detections` stream
- Homography engine (precomputed H matrix)
- Alert FSM (unknown person, person lost, crowd density)
- `reid_matches` audit writes
- `zone_presence` entry/exit tracking
