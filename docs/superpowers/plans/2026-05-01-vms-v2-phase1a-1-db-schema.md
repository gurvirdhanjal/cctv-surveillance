# VMS v2 Phase 1A — Database Schema, Project Scaffold, and Config

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE** — all 57 tests pass as of commit `4a4bc49`. See git log for delivered state.

**Goal:** Lay the project's structural foundation — a versioned PostgreSQL + pgvector schema covering every v2 table, a Pydantic-Settings configuration module, an SQLAlchemy session factory, and a CI-ready pytest scaffold. After this plan, the database is migrate-able and the package is importable; no inference or ingestion code is built yet.

**Architecture:** Single Python package `vms/` with a `db/` sub-package holding ORM models and the session factory. Alembic manages forward/backward schema migrations. PostgreSQL 16 + pgvector is the only backend — both tests and production. The test database runs in Docker (`pgvector/pgvector:pg16`, port 5434). All v2 tables ship in the **first** migration to avoid migration debt later.

**Tech Stack:** Python 3.10.11 · SQLAlchemy 2.x · Alembic 1.13 · psycopg2-binary 2.9.9 · pgvector 0.2.5 · pydantic-settings 2.x · pytest 8.x · pytest-asyncio 0.23 · black 24 · ruff 0.4 · mypy 1.10

**Spec reference:** `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` §10 (v1 schema), §B (camera tier columns), §C (anomaly_detectors + zone schedule), §D (maintenance_windows), §E (alert_dispatches + alert_routing), §F.2 (person_clip_embeddings), §F.3 (audit_log), §I (consolidated DDL summary).

---

## File Map

```
vms/
├── __init__.py
├── config.py                       # Settings via pydantic-settings, env-prefix VMS_
└── db/
    ├── __init__.py
    ├── session.py                  # engine + SessionLocal + get_db dependency
    └── models.py                   # All ORM models (Base + 17 tables)

alembic.ini
alembic/
├── env.py
├── script.py.mako
└── versions/
    └── 0001_initial_schema.py      # The full v2 schema as a single migration

tests/
├── __init__.py
├── conftest.py                     # env fixtures, PostgreSQL Docker engine (port 5434)
├── test_config.py                  # Settings load + defaults
├── test_db_session.py              # SessionLocal opens + closes
├── test_db_models_identity.py      # persons, person_embeddings, users, perms
├── test_db_models_topology.py      # cameras (v2 cols), zones (v2 cols)
├── test_db_models_tracking.py      # tracking_events, reid_matches, zone_presence
├── test_db_models_alerts.py        # alerts (v2 'suppressed' state), routing, dispatches
├── test_db_models_anomaly.py       # anomaly_detectors
├── test_db_models_maintenance.py   # maintenance_windows + constraints
├── test_db_models_forensic.py      # person_clip_embeddings
├── test_db_models_audit.py         # audit_log + hash-chain helper
└── test_migration.py               # alembic upgrade head + downgrade base

requirements.txt                    # rewritten
requirements-dev.txt                # NEW (dev tools: black, ruff, mypy, pytest-cov)
pyproject.toml                      # NEW (tool configs for black, ruff, mypy, pytest)
.gitignore                          # ensure venv/, __pycache__/, *.egg-info/, .pytest_cache/
```

**Existing files to leave alone (legacy prototype, will be removed in Phase 1B once vms/ replaces them):**
`main.py`, `face_detection.py`, `enrollment_emp.py`, `face_utils.py`, `scrfd_face.py`, `test.py`, `test_db.py`, `bytetrack_custom.yaml`, `config.py` (the legacy flat one — ours goes to `vms/config.py`).

---

## Pre-flight checks

- [x] **Step 0.1: Verify Python 3.10.11**

Run:
```powershell
python --version
```
Expected: `Python 3.10.11`. pydantic-settings 2.x requires ≥3.10.

- [x] **Step 0.2: Confirm PostgreSQL Docker test container is running**

```powershell
docker run -d --name vms-test-db --restart=unless-stopped `
    -e POSTGRES_PASSWORD=vms -e POSTGRES_DB=vms_test -e POSTGRES_USER=vms `
    -p 5434:5432 pgvector/pgvector:pg16
docker exec vms-test-db pg_isready -U vms -d vms_test
```
Expected: `/var/run/postgresql:5432 - accepting connections`. The container is configured with `--restart=unless-stopped` so it survives Docker Desktop restarts.

---

## Task 1: Project scaffold + dependencies

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-dev.txt`, `pyproject.toml`, `.gitignore`, `vms/__init__.py`, `vms/db/__init__.py`, `tests/__init__.py`, `tests/conftest.py`

- [ ] **Step 1.1: Replace `requirements.txt`**

Replace the entire current contents (5 lines) with:

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy==2.0.30
psycopg2-binary==2.9.9
pgvector==0.2.5
alembic==1.13.1
pydantic-settings==2.2.1
python-jose[cryptography]==3.3.0
bcrypt==4.1.3
redis==5.0.4
opencv-python-headless==4.9.0.80
numpy==1.26.4
onnxruntime-gpu==1.18.0
ultralytics==8.2.0
faiss-cpu==1.8.0
```

Reasoning: this lists every runtime dep across the whole VMS, not just Phase 1A. Pinning early prevents version drift later. ONNX/Redis/CV2 are unused until Phase 1B+ but having them locked here means future tasks just `pip install -r requirements.txt` and go.

- [ ] **Step 1.2: Create `requirements-dev.txt`**

```
pytest==8.2.0
pytest-asyncio==0.23.6
pytest-cov==5.0.0
httpx==0.27.0
black==24.4.2
ruff==0.4.4
mypy==1.10.0
sqlalchemy[mypy]==2.0.30
```

- [ ] **Step 1.3: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "vms"
version = "0.1.0"
description = "Video Management System with facial recognition and anomaly detection"
requires-python = ">=3.10"

[tool.black]
line-length = 100
target-version = ["py310"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "SIM", "RUF"]
ignore = ["E501"]  # black handles line length

[tool.mypy]
python_version = "3.10"
strict = true
plugins = ["sqlalchemy.ext.mypy.plugin"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "unit: fast in-process tests (default)",
    "integration: requires real PostgreSQL/Redis",
]
addopts = "-ra --strict-markers"
```

- [ ] **Step 1.4: Update `.gitignore`**

Append (create if not present):
```
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
.venv/
venv/
.env
.env.*
!.env.example
```

- [ ] **Step 1.5: Create empty package files**

```python
# vms/__init__.py
"""Video Management System package."""

__version__ = "0.1.0"
```

```python
# vms/db/__init__.py
"""Database layer: ORM models and session factory."""
```

```python
# tests/__init__.py
```

- [ ] **Step 1.6: Create `tests/conftest.py`**

```python
"""Shared pytest fixtures for the VMS test suite."""
from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _vms_env() -> Iterator[None]:
    """Provide deterministic env vars for every test."""
    with patch.dict(
        os.environ,
        {
            "VMS_DB_URL": "postgresql://vms:vms@localhost:5434/vms_test",
            "VMS_REDIS_URL": "redis://localhost:6379/0",
            "VMS_JWT_SECRET": "test-secret-do-not-use",
            "VMS_SCRFD_MODEL": "models/scrfd_2.5g.onnx",
            "VMS_ADAFACE_MODEL": "models/adaface_ir50.onnx",
            "VMS_BYTETRACK_CONFIG": "bytetrack_custom.yaml",
        },
        clear=False,
    ):
        yield
```

- [ ] **Step 1.7: Install everything**

```powershell
python -m pip install -U pip
pip install -r requirements.txt -r requirements-dev.txt
```
Expected: all packages install without error. `onnxruntime-gpu` requires CUDA — if unavailable, the install still succeeds; runtime fall-back to CPU is handled in later phases.

- [ ] **Step 1.8: Smoke test the scaffold**

```powershell
python -c "import vms; print(vms.__version__)"
```
Expected: `0.1.0`

```powershell
pytest -q
```
Expected: `no tests ran` (no errors). Confirms pyproject is discoverable and conftest loads cleanly.

- [ ] **Step 1.9: Commit**

```powershell
git add requirements.txt requirements-dev.txt pyproject.toml .gitignore vms/__init__.py vms/db/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: scaffold vms package, deps, and pytest config"
```

---

## Task 2: Settings module (vms/config.py)

**Files:**
- Create: `vms/config.py`, `tests/test_config.py`

- [ ] **Step 2.1: Write the failing test**

Create `tests/test_config.py`:

```python
"""Tests for vms.config.Settings."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from vms.config import Settings, get_settings


def test_settings_load_from_env() -> None:
    s = Settings()
    assert "postgresql" in s.db_url
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.jwt_secret == "test-secret-do-not-use"


def test_inference_threshold_defaults() -> None:
    s = Settings()
    assert s.scrfd_conf == 0.60
    assert s.adaface_min_sim == 0.72
    assert s.reid_cross_cam_sim == 0.65
    assert s.reid_margin == 0.08
    assert s.min_blur == 25.0
    assert s.min_face_px == 40


def test_pipeline_tuning_defaults() -> None:
    s = Settings()
    assert s.stale_threshold_ms == 200
    assert s.db_flush_rows == 100
    assert s.db_flush_ms == 500
    assert s.redis_stream_maxlen == 500


def test_get_settings_is_cached() -> None:
    a = get_settings()
    b = get_settings()
    assert a is b  # same instance


def test_missing_required_raises() -> None:
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(Exception):
            Settings()  # type: ignore[call-arg]
```

- [ ] **Step 2.2: Run — expect failure**

```powershell
pytest tests/test_config.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.config'`

- [ ] **Step 2.3: Implement `vms/config.py`**

```python
"""Application settings, loaded from environment variables prefixed VMS_."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="VMS_",
        case_sensitive=False,
        extra="ignore",
    )

    # connection strings — required
    db_url: str
    jwt_secret: str

    # connection strings — defaulted
    redis_url: str = "redis://localhost:6379/0"

    # model paths
    scrfd_model: str = "models/scrfd_2.5g.onnx"
    adaface_model: str = "models/adaface_ir50.onnx"
    bytetrack_config: str = "bytetrack_custom.yaml"

    # auth
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 8

    # inference thresholds (see spec v1 §6 + v2 §C)
    scrfd_conf: float = 0.60
    adaface_min_sim: float = 0.72
    reid_cross_cam_sim: float = 0.65
    reid_margin: float = 0.08
    min_blur: float = 25.0
    min_face_px: int = 40

    # pipeline tuning
    stale_threshold_ms: int = 200
    db_flush_rows: int = 100
    db_flush_ms: int = 500
    redis_stream_maxlen: int = 500


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 2.4: Run — expect pass**

```powershell
pytest tests/test_config.py -v
```
Expected: 5 passed.

- [ ] **Step 2.5: Format + lint**

```powershell
black vms/config.py tests/test_config.py
ruff check vms/config.py tests/test_config.py
mypy vms/config.py
```
All three should report clean.

- [ ] **Step 2.6: Commit**

```powershell
git add vms/config.py tests/test_config.py
git commit -m "feat(config): add Settings module backed by pydantic-settings"
```

---

## Task 3: Declarative Base + DB session factory

**Files:**
- Create: `vms/db/session.py`, `tests/test_db_session.py`

- [ ] **Step 3.1: Write the failing test**

Create `tests/test_db_session.py`:

```python
"""Tests for vms.db.session — engine, SessionLocal, get_db dependency."""
from __future__ import annotations

from sqlalchemy import text

from vms.db.session import Base, SessionLocal, engine, get_db


def test_engine_is_configured() -> None:
    assert engine is not None
    assert "postgresql" in str(engine.url)


def test_base_has_metadata() -> None:
    assert Base.metadata is not None


def test_session_can_execute_simple_query() -> None:
    with SessionLocal() as s:
        result = s.execute(text("SELECT 1")).scalar_one()
    assert result == 1


def test_get_db_yields_and_closes() -> None:
    gen = get_db()
    s = next(gen)
    s.execute(text("SELECT 1"))
    try:
        next(gen)
    except StopIteration:
        pass  # expected: generator exhausts after the single yield
```

- [ ] **Step 3.2: Run — expect failure**

```powershell
pytest tests/test_db_session.py -v
```
Expected: `ImportError: cannot import name 'Base' from 'vms.db.session'`

- [ ] **Step 3.3: Implement `vms/db/session.py`**

```python
"""SQLAlchemy engine, declarative Base, session factory, and FastAPI dependency."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from vms.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.db_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    with SessionLocal() as session:
        yield session
```

- [ ] **Step 3.4: Run — expect pass**

```powershell
pytest tests/test_db_session.py -v
```
Expected: 4 passed.

- [ ] **Step 3.5: Format, lint, commit**

```powershell
black vms/db/session.py tests/test_db_session.py
ruff check vms/db/session.py tests/test_db_session.py
mypy vms/db/session.py
git add vms/db/session.py tests/test_db_session.py
git commit -m "feat(db): add SQLAlchemy engine, Base, and SessionLocal"
```

---

## Task 4: Identity domain ORM models (persons, person_embeddings, users, permissions)

**Files:**
- Create: `vms/db/models.py`, `tests/test_db_models_identity.py`

- [ ] **Step 4.1: Write the failing test**

Create `tests/test_db_models_identity.py`:

```python
"""Tests for identity-domain ORM models."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from vms.db.models import (
    Person,
    PersonEmbedding,
    User,
    UserCameraPermission,
    UserZonePermission,
)
from vms.db.session import Base, SessionLocal, engine


@pytest.fixture(autouse=True)
def _create_tables() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_create_person_with_embeddings() -> None:
    with SessionLocal() as s:
        p = Person(
            employee_id="EMP-001",
            full_name="Alice",
            department="QA",
            person_type="employee",
        )
        p.embeddings.append(
            PersonEmbedding(embedding=b"\x00" * 2048, quality_score=0.9, source="enrollment")
        )
        s.add(p)
        s.commit()

        loaded = s.query(Person).filter_by(employee_id="EMP-001").one()
        assert loaded.is_active is True
        assert len(loaded.embeddings) == 1
        assert loaded.embeddings[0].quality_score == pytest.approx(0.9)


def test_user_username_unique() -> None:
    with SessionLocal() as s:
        s.add(User(username="alice", email="a@x", password_hash="h", role="guard"))
        s.add(User(username="alice", email="b@x", password_hash="h", role="guard"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_zone_permission_composite_pk() -> None:
    with SessionLocal() as s:
        u = User(username="bob", email="b@x", password_hash="h", role="guard")
        s.add(u)
        s.flush()
        s.add(UserZonePermission(user_id=u.user_id, zone_id=1))
        s.add(UserZonePermission(user_id=u.user_id, zone_id=1))  # duplicate
        with pytest.raises(IntegrityError):
            s.commit()


def test_camera_permission_composite_pk() -> None:
    with SessionLocal() as s:
        u = User(username="carol", email="c@x", password_hash="h", role="manager")
        s.add(u)
        s.flush()
        s.add(UserCameraPermission(user_id=u.user_id, camera_id=1))
        s.add(UserCameraPermission(user_id=u.user_id, camera_id=1))
        with pytest.raises(IntegrityError):
            s.commit()


def test_person_created_at_default_now() -> None:
    before = datetime.now(timezone.utc)
    with SessionLocal() as s:
        p = Person(employee_id="EMP-002", full_name="Dave", person_type="visitor")
        s.add(p)
        s.commit()
        assert p.created_at is not None
        # tolerant comparison — DB clock vs Python clock skew
        assert p.created_at.replace(tzinfo=None) >= before.replace(tzinfo=None)
```

- [ ] **Step 4.2: Run — expect failure**

```powershell
pytest tests/test_db_models_identity.py -v
```
Expected: `ImportError: cannot import name 'Person' from 'vms.db.models'`

- [ ] **Step 4.3: Implement `vms/db/models.py` — identity tables**

Start the file with the imports and Base re-export, then add the identity domain models. (More tables added in Tasks 5–10; keep the file growing — do not split prematurely. Threshold for splitting is ~600 lines.)

```python
"""ORM models for every VMS table.

Layout follows spec §10 (v1) and §B/§C/§D/§E/§F.2/§F.3 (v2 additions).
High-volume PKs (embedding_id, event_id, reid_match_id, presence_id, dispatch_id, clip_emb_id, audit_id) use BigInteger (BIGSERIAL on PostgreSQL). Embedding columns use pgvector Vector(512).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vms.db.session import Base

# ---------------------------------------------------------------------------
# Identity domain
# ---------------------------------------------------------------------------


class Person(Base):
    """Registered employees and unknown visitor records (spec §10)."""

    __tablename__ = "persons"

    person_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    person_type: Mapped[str] = mapped_column(String(20), nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    purged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    embeddings: Mapped[list["PersonEmbedding"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )


class PersonEmbedding(Base):
    """Multiple face embeddings per person; FAISS rebuilt from this table at startup."""

    __tablename__ = "person_embeddings"

    embedding_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False, index=True
    )
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    person: Mapped[Person] = relationship(back_populates="embeddings")


class User(Base):
    """System users — guards, managers, admins."""

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserZonePermission(Base):
    __tablename__ = "user_zone_permissions"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    zone_id: Mapped[int] = mapped_column(Integer, primary_key=True)


class UserCameraPermission(Base):
    __tablename__ = "user_camera_permissions"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )
    camera_id: Mapped[int] = mapped_column(Integer, primary_key=True)
```

- [ ] **Step 4.4: Run — expect pass**

```powershell
pytest tests/test_db_models_identity.py -v
```
Expected: 5 passed.

- [ ] **Step 4.5: Format, lint, commit**

```powershell
black vms/db/models.py tests/test_db_models_identity.py
ruff check vms/db/models.py tests/test_db_models_identity.py
mypy vms/db/models.py
git add vms/db/models.py tests/test_db_models_identity.py
git commit -m "feat(db): add identity-domain ORM models (persons, embeddings, users, permissions)"
```

---

## Task 5: Topology models — `cameras` and `zones` (with v2 columns)

**Files:**
- Modify: `vms/db/models.py` (append)
- Create: `tests/test_db_models_topology.py`

- [ ] **Step 5.1: Write the failing test**

Create `tests/test_db_models_topology.py`:

```python
"""Tests for camera + zone ORM models including v2 columns."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from vms.db.models import Camera, Zone
from vms.db.session import Base, SessionLocal, engine


@pytest.fixture(autouse=True)
def _create_tables() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_camera_defaults_to_full_tier() -> None:
    with SessionLocal() as s:
        c = Camera(
            name="Loading Bay 1",
            rtsp_url="rtsp://10.0.0.1/stream",
            worker_group="A",
            resolution_w=1920,
            resolution_h=1080,
        )
        s.add(c)
        s.commit()
        assert c.capability_tier == "FULL"
        assert c.is_active is True
        assert c.profile_data is None
        assert c.profiled_at is None
        assert c.model_overrides is None


def test_camera_invalid_tier_rejected() -> None:
    with SessionLocal() as s:
        s.add(
            Camera(
                name="Bad",
                rtsp_url="rtsp://x",
                worker_group="A",
                resolution_w=640,
                resolution_h=480,
                capability_tier="EXTREME",  # not in {FULL, MID, LOW}
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_zone_defaults_for_v2_columns() -> None:
    with SessionLocal() as s:
        z = Zone(name="Welding Bay", polygon='[[0,0],[1,0],[1,1],[0,1]]', color_hex="#ff0000")
        s.add(z)
        s.commit()
        assert z.is_restricted is False
        assert z.loiter_threshold_s == 180  # v2 default
        assert z.allowed_hours is None  # v2 nullable


def test_zone_loiter_threshold_overridable() -> None:
    with SessionLocal() as s:
        z = Zone(name="Cafeteria", polygon="[]", color_hex="#00ff00", loiter_threshold_s=600)
        s.add(z)
        s.commit()
        assert z.loiter_threshold_s == 600
```

- [ ] **Step 5.2: Run — expect failure**

```powershell
pytest tests/test_db_models_topology.py -v
```
Expected: `ImportError: cannot import name 'Camera' from 'vms.db.models'`

- [ ] **Step 5.3: Append camera + zone models to `vms/db/models.py`**

Append after the identity domain block:

```python
# ---------------------------------------------------------------------------
# Topology domain — cameras (with v2 capability tier) and zones (with v2 schedule)
# ---------------------------------------------------------------------------


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        CheckConstraint(
            "capability_tier IN ('FULL', 'MID', 'LOW')",
            name="chk_camera_tier",
        ),
    )

    camera_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rtsp_url: Mapped[str] = mapped_column(String(500), nullable=False)
    worker_group: Mapped[str] = mapped_column(String(1), nullable=False)
    homography_matrix: Mapped[str | None] = mapped_column(Text, nullable=True)
    fov_polygon: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_w: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_h: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # v2 §B + §L additions
    capability_tier: Mapped[str] = mapped_column(String(10), nullable=False, default="FULL")
    profile_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    profiled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    model_overrides: Mapped[str | None] = mapped_column(Text, nullable=True)


class Zone(Base):
    __tablename__ = "zones"

    zone_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    polygon: Mapped[str] = mapped_column(Text, nullable=False)
    max_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    adjacent_zone_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    color_hex: Mapped[str] = mapped_column(String(7), nullable=False)

    # v2 §C additions
    allowed_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    loiter_threshold_s: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
```

- [ ] **Step 5.4: Run — expect pass**

```powershell
pytest tests/test_db_models_topology.py -v
```
Expected: 4 passed.

- [ ] **Step 5.5: Format, lint, commit**

```powershell
black vms/db/models.py tests/test_db_models_topology.py
ruff check vms/db/models.py tests/test_db_models_topology.py
mypy vms/db/models.py
git add vms/db/models.py tests/test_db_models_topology.py
git commit -m "feat(db): add camera + zone models with v2 capability tier and zone schedule"
```

---

## Task 6: Tracking domain — `tracking_events`, `reid_matches`, `zone_presence`

**Files:**
- Modify: `vms/db/models.py` (append)
- Create: `tests/test_db_models_tracking.py`

- [ ] **Step 6.1: Write the failing test**

```python
"""Tests for tracking-domain ORM models."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from vms.db.models import Camera, ReidMatch, TrackingEvent, Zone, ZonePresence
from vms.db.session import Base, SessionLocal, engine


@pytest.fixture(autouse=True)
def _create_tables() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _make_camera(s, name: str = "C1") -> Camera:
    c = Camera(
        name=name,
        rtsp_url="rtsp://x",
        worker_group="A",
        resolution_w=1920,
        resolution_h=1080,
    )
    s.add(c)
    s.flush()
    return c


def test_tracking_event_idempotency_constraint() -> None:
    with SessionLocal() as s:
        c = _make_camera(s)
        ts = datetime.now(timezone.utc).replace(tzinfo=None)
        t1 = TrackingEvent(
            global_track_id=str(uuid4()),
            camera_id=c.camera_id,
            local_track_id=42,
            bbox_x1=10,
            bbox_y1=20,
            bbox_x2=110,
            bbox_y2=220,
            confidence=0.9,
            event_ts=ts,
        )
        t2 = TrackingEvent(
            global_track_id=str(uuid4()),
            camera_id=c.camera_id,
            local_track_id=42,
            bbox_x1=11,
            bbox_y1=21,
            bbox_x2=111,
            bbox_y2=221,
            confidence=0.8,
            event_ts=ts,  # same (camera_id, local_track_id, event_ts) — should violate unique
        )
        s.add_all([t1, t2])
        with pytest.raises(IntegrityError):
            s.commit()


def test_reid_match_logged() -> None:
    with SessionLocal() as s:
        c1, c2 = _make_camera(s, "C1"), _make_camera(s, "C2")
        m = ReidMatch(
            global_track_id=str(uuid4()),
            person_id=1,
            confidence=0.81,
            match_source="auto",
            from_camera_id=c1.camera_id,
            to_camera_id=c2.camera_id,
        )
        s.add(m)
        s.commit()
        assert m.match_id is not None
        assert m.matched_at is not None


def test_zone_presence_open_until_exit() -> None:
    with SessionLocal() as s:
        z = Zone(name="A", polygon="[]", color_hex="#000000")
        s.add(z)
        s.flush()
        gtid = str(uuid4())
        entered = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
        zp = ZonePresence(zone_id=z.zone_id, global_track_id=gtid, entered_at=entered)
        s.add(zp)
        s.commit()
        assert zp.exited_at is None
```

- [ ] **Step 6.2: Run — expect failure**

```powershell
pytest tests/test_db_models_tracking.py -v
```
Expected: `ImportError: cannot import name 'TrackingEvent' from 'vms.db.models'`

- [ ] **Step 6.3: Append tracking models to `vms/db/models.py`**

```python
# ---------------------------------------------------------------------------
# Tracking domain — events, re-id audit, zone presence
# ---------------------------------------------------------------------------


class TrackingEvent(Base):
    """High-write event log. Idempotent on (camera_id, local_track_id, event_ts)."""

    __tablename__ = "tracking_events"
    __table_args__ = (
        UniqueConstraint(
            "camera_id", "local_track_id", "event_ts", name="uq_tracking_idem"
        ),
    )

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    global_track_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.person_id"), nullable=True, index=True
    )
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.camera_id"), nullable=False, index=True
    )
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    local_track_id: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_x1: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_y1: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_x2: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_y2: Mapped[int] = mapped_column(Integer, nullable=False)
    floor_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    floor_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    event_ts: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(), index=True
    )


class ReidMatch(Base):
    """Audit trail of every cross-camera re-identification decision."""

    __tablename__ = "reid_matches"

    match_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    global_track_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.person_id"), nullable=False, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    match_source: Mapped[str] = mapped_column(String(20), nullable=False)
    from_camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.camera_id"))
    to_camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.camera_id"))
    matched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class ZonePresence(Base):
    """Dwell records for analytics + heatmaps. exited_at NULL = currently inside."""

    __tablename__ = "zone_presence"

    presence_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    zone_id: Mapped[int] = mapped_column(
        ForeignKey("zones.zone_id"), nullable=False, index=True
    )
    global_track_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.person_id"), nullable=True, index=True
    )
    entered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    exited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 6.4: Run — expect pass**

```powershell
pytest tests/test_db_models_tracking.py -v
```
Expected: 3 passed.

- [ ] **Step 6.5: Format, lint, commit**

```powershell
black vms/db/models.py tests/test_db_models_tracking.py
ruff check vms/db/models.py tests/test_db_models_tracking.py
mypy vms/db/models.py
git add vms/db/models.py tests/test_db_models_tracking.py
git commit -m "feat(db): add tracking_events, reid_matches, zone_presence models"
```

---

## Task 7: Alert domain — `alerts` (with v2 'suppressed' state), `alert_routing`, `alert_dispatches`

> **DEPENDENCY ORDER:** `Alert.suppressed_by_window_id` is a ForeignKey to `maintenance_windows`, defined in Task 9. SQLAlchemy resolves FK string references at `Base.metadata.create_all()` time — if `MaintenanceWindow` is not in metadata when this task's test runs, you get `NoReferencedTableError`. **Execute Task 9 (Maintenance windows) FIRST, then return here.** Tasks 8 (AnomalyDetector) and 10+ have no such dependency and can run in normal order.

**Files:**
- Modify: `vms/db/models.py` (append)
- Create: `tests/test_db_models_alerts.py`

- [ ] **Step 7.1: Write the failing test**

```python
"""Tests for alert-domain ORM models including v2 dispatcher tables."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from vms.db.models import Alert, AlertDispatch, AlertRouting
from vms.db.session import Base, SessionLocal, engine


@pytest.fixture(autouse=True)
def _create_tables() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_alert_state_enum_includes_suppressed() -> None:
    with SessionLocal() as s:
        a = Alert(
            state="suppressed",  # v2 added value
            alert_type="UNKNOWN_PERSON",
            severity="HIGH",
            triggered_at=__import__("datetime").datetime.utcnow(),
        )
        s.add(a)
        s.commit()
        assert a.alert_id is not None


def test_alert_invalid_state_rejected() -> None:
    with SessionLocal() as s:
        s.add(
            Alert(
                state="bogus",
                alert_type="UNKNOWN_PERSON",
                severity="HIGH",
                triggered_at=__import__("datetime").datetime.utcnow(),
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_alert_routing_channel_constraint() -> None:
    with SessionLocal() as s:
        s.add(
            AlertRouting(
                alert_type="VIOLENCE",
                severity="CRITICAL",
                channel="EMAIL",
                target="security@example.com",
            )
        )
        s.commit()
        # invalid channel
        s.add(
            AlertRouting(
                alert_type=None,
                severity=None,
                channel="CARRIER_PIGEON",
                target="x",
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_alert_dispatch_records_attempt() -> None:
    with SessionLocal() as s:
        a = Alert(
            state="active",
            alert_type="INTRUSION",
            severity="CRITICAL",
            triggered_at=__import__("datetime").datetime.utcnow(),
        )
        s.add(a)
        s.flush()
        s.add(
            AlertDispatch(
                alert_id=a.alert_id,
                channel="WEBHOOK",
                target="https://hook.example.com/vms",
                attempt_n=1,
                success=True,
                response_code=200,
            )
        )
        s.commit()
```

- [ ] **Step 7.2: Run — expect failure**

```powershell
pytest tests/test_db_models_alerts.py -v
```
Expected: import error for `Alert`.

- [ ] **Step 7.3: Append alert models to `vms/db/models.py`**

```python
# ---------------------------------------------------------------------------
# Alert domain — alerts + v2 dispatcher (routing + dispatches)
# ---------------------------------------------------------------------------


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "state IN ('active', 'acknowledged', 'resolved', 'suppressed')",
            name="chk_alert_state",
        ),
    )

    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("persons.person_id"))
    global_track_id: Mapped[str | None] = mapped_column(String(36))
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.camera_id"))
    zone_id: Mapped[int | None] = mapped_column(Integer)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    snapshot_path: Mapped[str | None] = mapped_column(String(500))

    # v2 §D — link to maintenance window if suppressed
    suppressed_by_window_id: Mapped[int | None] = mapped_column(
        ForeignKey("maintenance_windows.window_id"), nullable=True
    )


class AlertRouting(Base):
    """Per-alert-type/severity/zone routing rules. NULL = wildcard."""

    __tablename__ = "alert_routing"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('EMAIL','SLACK','TELEGRAM','WEBHOOK','WEBSOCKET')",
            name="chk_routing_channel",
        ),
    )

    routing_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(10), nullable=True)
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AlertDispatch(Base):
    """Per-attempt audit of alert delivery to each channel."""

    __tablename__ = "alert_dispatches"

    dispatch_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.alert_id"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    attempt_n: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dispatched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 7.4: Run — expect pass**

```powershell
pytest tests/test_db_models_alerts.py -v
```
Expected: 4 passed. (Task 9 should already be done per the dependency note at the top of this task — `MaintenanceWindow` is registered in `Base.metadata` so SQLAlchemy can resolve the `suppressed_by_window_id` FK.)

- [ ] **Step 7.5: Format, lint, commit**

```powershell
black vms/db/models.py tests/test_db_models_alerts.py
ruff check vms/db/models.py tests/test_db_models_alerts.py
mypy vms/db/models.py
git add vms/db/models.py tests/test_db_models_alerts.py
git commit -m "feat(db): add alert + alert_routing + alert_dispatches models"
```

---

## Task 8: Anomaly detector registry — `anomaly_detectors`

**Files:**
- Modify: `vms/db/models.py` (append)
- Create: `tests/test_db_models_anomaly.py`

- [ ] **Step 8.1: Write the failing test**

```python
"""Tests for anomaly_detectors model — registry of pluggable detector classes."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from vms.db.models import AnomalyDetector
from vms.db.session import Base, SessionLocal, engine


@pytest.fixture(autouse=True)
def _create_tables() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_register_detector() -> None:
    with SessionLocal() as s:
        d = AnomalyDetector(
            alert_type="VIOLENCE",
            class_path="vms.anomaly.violence.ViolenceDetector",
            config_json='{"threshold": 0.65}',
            model_version="movinet_a0_v1.0.0",
        )
        s.add(d)
        s.commit()
        assert d.detector_id is not None
        assert d.is_enabled is True


def test_alert_type_must_be_unique() -> None:
    with SessionLocal() as s:
        s.add(AnomalyDetector(alert_type="VIOLENCE", class_path="a.b.C"))
        s.add(AnomalyDetector(alert_type="VIOLENCE", class_path="a.b.D"))
        with pytest.raises(IntegrityError):
            s.commit()
```

- [ ] **Step 8.2: Run — expect failure**

```powershell
pytest tests/test_db_models_anomaly.py -v
```
Expected: import error.

- [ ] **Step 8.3: Append `AnomalyDetector` model**

```python
# ---------------------------------------------------------------------------
# Anomaly registry (v2 §C)
# ---------------------------------------------------------------------------


class AnomalyDetector(Base):
    """Registry row for each pluggable detector class."""

    __tablename__ = "anomaly_detectors"

    detector_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    class_path: Mapped[str] = mapped_column(String(200), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
```

- [ ] **Step 8.4: Run — expect pass**

```powershell
pytest tests/test_db_models_anomaly.py -v
```
Expected: 2 passed.

- [ ] **Step 8.5: Format, lint, commit**

```powershell
black vms/db/models.py tests/test_db_models_anomaly.py
ruff check vms/db/models.py tests/test_db_models_anomaly.py
mypy vms/db/models.py
git add vms/db/models.py tests/test_db_models_anomaly.py
git commit -m "feat(db): add anomaly_detectors registry model"
```

---

## Task 9: Maintenance windows — `maintenance_windows`

**Files:**
- Modify: `vms/db/models.py` (append)
- Create: `tests/test_db_models_maintenance.py`

- [ ] **Step 9.1: Write the failing test**

```python
"""Tests for maintenance_windows model + check constraints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from vms.db.models import MaintenanceWindow, User
from vms.db.session import Base, SessionLocal, engine


@pytest.fixture(autouse=True)
def _create_tables() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _make_user(s) -> int:
    u = User(username="admin", email="a@x", password_hash="h", role="admin")
    s.add(u)
    s.flush()
    return u.user_id


def test_one_time_window_requires_starts_and_ends() -> None:
    with SessionLocal() as s:
        uid = _make_user(s)
        # missing ends_at → constraint violation
        s.add(
            MaintenanceWindow(
                name="Cleanup",
                scope_type="CAMERA",
                scope_id=1,
                schedule_type="ONE_TIME",
                starts_at=datetime.now(timezone.utc).replace(tzinfo=None),
                ends_at=None,
                created_by=uid,
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_recurring_window_requires_cron_and_duration() -> None:
    with SessionLocal() as s:
        uid = _make_user(s)
        # missing duration_minutes → constraint violation
        s.add(
            MaintenanceWindow(
                name="Saturday cleaning",
                scope_type="ZONE",
                scope_id=1,
                schedule_type="RECURRING",
                cron_expr="0 14 * * 6",
                duration_minutes=None,
                created_by=uid,
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_invalid_scope_rejected() -> None:
    with SessionLocal() as s:
        uid = _make_user(s)
        s.add(
            MaintenanceWindow(
                name="Bogus",
                scope_type="UNIVERSE",  # not in {CAMERA, ZONE}
                scope_id=1,
                schedule_type="ONE_TIME",
                starts_at=datetime.now(timezone.utc).replace(tzinfo=None),
                ends_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
                created_by=uid,
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


def test_recurring_window_happy_path() -> None:
    with SessionLocal() as s:
        uid = _make_user(s)
        w = MaintenanceWindow(
            name="Weekly maintenance",
            scope_type="ZONE",
            scope_id=1,
            schedule_type="RECURRING",
            cron_expr="0 14 * * 6",
            duration_minutes=120,
            reason="scheduled cleaning",
            created_by=uid,
        )
        s.add(w)
        s.commit()
        assert w.window_id is not None
        assert w.is_active is True
```

- [ ] **Step 9.2: Run — expect failure**

```powershell
pytest tests/test_db_models_maintenance.py -v
```
Expected: import error.

- [ ] **Step 9.3: Append `MaintenanceWindow` model**

```python
# ---------------------------------------------------------------------------
# Maintenance windows (v2 §D)
# ---------------------------------------------------------------------------


class MaintenanceWindow(Base):
    """Suppression schedule for alerts during planned downtime."""

    __tablename__ = "maintenance_windows"
    __table_args__ = (
        CheckConstraint("scope_type IN ('CAMERA', 'ZONE')", name="chk_mw_scope"),
        CheckConstraint(
            "schedule_type IN ('ONE_TIME', 'RECURRING')", name="chk_mw_sched"
        ),
        CheckConstraint(
            "schedule_type <> 'ONE_TIME' OR (starts_at IS NOT NULL AND ends_at IS NOT NULL)",
            name="chk_mw_one_time",
        ),
        CheckConstraint(
            "schedule_type <> 'RECURRING' OR (cron_expr IS NOT NULL AND duration_minutes IS NOT NULL)",
            name="chk_mw_recurring",
        ),
    )

    window_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[int] = mapped_column(Integer, nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cron_expr: Mapped[str | None] = mapped_column(String(100), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suppress_alert_types: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
```

- [ ] **Step 9.4: Run — expect pass**

```powershell
pytest tests/test_db_models_maintenance.py -v
```
Expected: 4 passed. With `MaintenanceWindow` now in `Base.metadata`, **Task 7 (Alerts) can now be executed safely** — its FK to `maintenance_windows.window_id` will resolve.

- [ ] **Step 9.5: Format, lint, commit**

```powershell
black vms/db/models.py tests/test_db_models_maintenance.py
ruff check vms/db/models.py tests/test_db_models_maintenance.py
mypy vms/db/models.py
git add vms/db/models.py tests/test_db_models_maintenance.py
git commit -m "feat(db): add maintenance_windows model with check constraints"
```

---

## Task 10: Forensic CLIP embeddings — `person_clip_embeddings`

**Files:**
- Modify: `vms/db/models.py` (append)
- Create: `tests/test_db_models_forensic.py`

- [ ] **Step 10.1: Write the failing test**

```python
"""Tests for person_clip_embeddings model (v2 §F.2 forensic search)."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from vms.db.models import Camera, PersonClipEmbedding
from vms.db.session import Base, SessionLocal, engine


@pytest.fixture(autouse=True)
def _create_tables() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_clip_embedding_persists() -> None:
    with SessionLocal() as s:
        c = Camera(
            name="C1",
            rtsp_url="rtsp://x",
            worker_group="A",
            resolution_w=1920,
            resolution_h=1080,
        )
        s.add(c)
        s.flush()
        emb = PersonClipEmbedding(
            global_track_id=str(uuid4()),
            camera_id=c.camera_id,
            event_ts=datetime.now(timezone.utc).replace(tzinfo=None),
            embedding=b"\x00" * 2048,
            snapshot_path="/var/snapshots/2026-05-01/track_abc.jpg",
        )
        s.add(emb)
        s.commit()
        assert emb.clip_emb_id is not None
```

- [ ] **Step 10.2: Run — expect failure**

```powershell
pytest tests/test_db_models_forensic.py -v
```
Expected: import error.

- [ ] **Step 10.3: Append `PersonClipEmbedding`**

```python
# ---------------------------------------------------------------------------
# Forensic CLIP search (v2 §F.2)
# ---------------------------------------------------------------------------


class PersonClipEmbedding(Base):
    """CLIP-ViT-B/32 embedding per detected person crop, indexed in FAISS at startup."""

    __tablename__ = "person_clip_embeddings"

    clip_emb_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    global_track_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.camera_id"), nullable=False
    )
    event_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    snapshot_path: Mapped[str] = mapped_column(String(500), nullable=False)
```

- [ ] **Step 10.4: Run — expect pass**

```powershell
pytest tests/test_db_models_forensic.py -v
```
Expected: 1 passed.

- [ ] **Step 10.5: Format, lint, commit**

```powershell
black vms/db/models.py tests/test_db_models_forensic.py
ruff check vms/db/models.py tests/test_db_models_forensic.py
mypy vms/db/models.py
git add vms/db/models.py tests/test_db_models_forensic.py
git commit -m "feat(db): add person_clip_embeddings model"
```

---

## Task 11: Audit log — `audit_log` (with hash-chain helper)

**Files:**
- Modify: `vms/db/models.py` (append)
- Create: `vms/db/audit.py`, `tests/test_db_models_audit.py`

- [ ] **Step 11.1: Write the failing test**

```python
"""Tests for audit_log model + hash-chain helper."""
from __future__ import annotations

import hashlib
import json

import pytest

from vms.db.audit import GENESIS_HASH, compute_row_hash, write_audit_event
from vms.db.models import AuditLog
from vms.db.session import Base, SessionLocal, engine


@pytest.fixture(autouse=True)
def _create_tables() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_genesis_hash_is_64_zeros() -> None:
    assert GENESIS_HASH == "0" * 64


def test_compute_row_hash_is_deterministic() -> None:
    h1 = compute_row_hash(
        prev_hash=GENESIS_HASH,
        event_type="ALERT_FIRED",
        actor_user_id=None,
        target_type="alert",
        target_id="42",
        payload='{"severity":"HIGH"}',
        event_ts="2026-05-01T10:00:00",
    )
    h2 = compute_row_hash(
        prev_hash=GENESIS_HASH,
        event_type="ALERT_FIRED",
        actor_user_id=None,
        target_type="alert",
        target_id="42",
        payload='{"severity":"HIGH"}',
        event_ts="2026-05-01T10:00:00",
    )
    assert h1 == h2
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)


def test_first_audit_row_links_to_genesis() -> None:
    with SessionLocal() as s:
        row = write_audit_event(
            s,
            event_type="OPERATOR_ACK",
            actor_user_id=1,
            target_type="alert",
            target_id="42",
            payload={"note": "false positive"},
        )
        s.commit()
        assert row.prev_hash == GENESIS_HASH
        assert len(row.row_hash) == 64


def test_chain_links_correctly() -> None:
    with SessionLocal() as s:
        r1 = write_audit_event(s, event_type="A")
        s.commit()
        r2 = write_audit_event(s, event_type="B")
        s.commit()
        assert r2.prev_hash == r1.row_hash
```

- [ ] **Step 11.2: Run — expect failure**

```powershell
pytest tests/test_db_models_audit.py -v
```
Expected: import error.

- [ ] **Step 11.3: Append `AuditLog` model**

```python
# ---------------------------------------------------------------------------
# Audit log with hash-chain (v2 §F.3)
# ---------------------------------------------------------------------------


class AuditLog(Base):
    """Append-only event log with SHA-256 hash-chain for tamper detection."""

    __tablename__ = "audit_log"

    audit_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    target_type: Mapped[str | None] = mapped_column(String(50))
    target_id: Mapped[str | None] = mapped_column(String(50))
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_ts: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(), index=True
    )
```

- [ ] **Step 11.4: Create `vms/db/audit.py`**

```python
"""Hash-chain helpers for the immutable audit_log table (spec §F.3)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from vms.db.models import AuditLog

GENESIS_HASH = "0" * 64


def compute_row_hash(
    *,
    prev_hash: str,
    event_type: str,
    actor_user_id: int | None,
    target_type: str | None,
    target_id: str | None,
    payload: str | None,
    event_ts: str,
) -> str:
    """Deterministic SHA-256 over a canonical concatenation of audit-row fields."""
    parts = "|".join(
        [
            prev_hash,
            event_type,
            "" if actor_user_id is None else str(actor_user_id),
            target_type or "",
            target_id or "",
            payload or "",
            event_ts,
        ]
    )
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


def write_audit_event(
    session: Session,
    *,
    event_type: str,
    actor_user_id: int | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    """Append an audit event with the hash-chain wired correctly.

    Caller is responsible for `session.commit()`; this function only adds + flushes.
    """
    last = (
        session.query(AuditLog)
        .order_by(AuditLog.audit_id.desc())
        .limit(1)
        .one_or_none()
    )
    prev = last.row_hash if last is not None else GENESIS_HASH
    payload_str = None if payload is None else json.dumps(payload, sort_keys=True)

    # Use Python clock for event_ts so the hash is deterministic before insert.
    # DB server_default would create a chicken-and-egg problem (need ts to compute hash).
    now = datetime.utcnow()
    ts_iso = now.isoformat(timespec="microseconds")
    row_hash = compute_row_hash(
        prev_hash=prev,
        event_type=event_type,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        payload=payload_str,
        event_ts=ts_iso,
    )

    row = AuditLog(
        event_type=event_type,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        payload=payload_str,
        prev_hash=prev,
        row_hash=row_hash,
        event_ts=now,
    )
    session.add(row)
    session.flush()
    return row
```

- [ ] **Step 11.5: Run — expect pass**

```powershell
pytest tests/test_db_models_audit.py -v
```
Expected: 4 passed.

- [ ] **Step 11.6: Format, lint, commit**

```powershell
black vms/db/models.py vms/db/audit.py tests/test_db_models_audit.py
ruff check vms/db/models.py vms/db/audit.py tests/test_db_models_audit.py
mypy vms/db/models.py vms/db/audit.py
git add vms/db/models.py vms/db/audit.py tests/test_db_models_audit.py
git commit -m "feat(db): add audit_log model + hash-chain write helper"
```

---

## Task 12: Run the full test suite as a coherence check

- [ ] **Step 12.1: Run everything**

```powershell
pytest -v
```
Expected: every test in tests/test_db_models_*.py + test_config.py + test_db_session.py passes. Tally ≈ 30 tests, all green.

- [ ] **Step 12.2: Check coverage**

```powershell
pytest --cov=vms --cov-report=term-missing
```
Expected: `vms/db/models.py` coverage ≥ 80%; `vms/config.py` 100%; `vms/db/session.py` ≥ 70%; `vms/db/audit.py` ≥ 90%.

If coverage falls below threshold, add a targeted test for the missing branch — do not lower the threshold.

- [ ] **Step 12.3: Lint + type-check entire package**

```powershell
black --check vms/ tests/
ruff check vms/ tests/
mypy vms/
```
All clean.

---

## Task 13: Alembic setup + initial migration

**Files:**
- Create: `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_initial_schema.py`
- Create: `tests/test_migration.py`

- [ ] **Step 13.1: Initialise Alembic**

```powershell
alembic init alembic
```
Expected: creates `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/`. Note that alembic init writes default content — we replace the relevant files in the next steps.

- [ ] **Step 13.2: Edit `alembic.ini`**

Find the line `sqlalchemy.url =` and replace it with:

```
# DB URL is set programmatically from VMS_DB_URL in alembic/env.py
sqlalchemy.url =
```

Set:
```
[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic
```

- [ ] **Step 13.3: Replace `alembic/env.py` contents**

```python
"""Alembic env wired to vms.config + vms.db.models."""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from vms.config import get_settings
from vms.db.models import Base  # noqa: F401  -- registers all tables on import

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from settings (env var VMS_DB_URL)
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 13.4: Create the initial migration manually**

We write the migration by hand rather than autogenerating, because:
1. The first migration includes 17 tables — autogen output is verbose and we want clean ordering.
2. pgvector `Vector(512)` columns and `HNSW` index require explicit DDL that autogen doesn't emit.
3. Hand-written first migrations are easier to review and audit.

Create `alembic/versions/0001_initial_schema.py`:

```python
"""Initial VMS v2 schema — all tables, indexes, constraints, pgvector types.

Revision ID: 0001
Revises:
Create Date: 2026-05-08

Ships every v2 table in one migration to avoid migration debt during
foundation development. PostgreSQL + pgvector only — no dialect branching.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # ----- identity domain -----
    op.create_table(
        "users",
        sa.Column("user_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("email", sa.String(200), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.Column("last_login", sa.DateTime, nullable=True),
    )

    op.create_table(
        "persons",
        sa.Column("person_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("employee_id", sa.String(50), nullable=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("person_type", sa.String(20), nullable=False),
        sa.Column("thumbnail_path", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.Column("purged_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_persons_employee_id", "persons", ["employee_id"])

    op.create_table(
        "person_embeddings",
        sa.Column("embedding_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "person_id",
            sa.Integer,
            sa.ForeignKey("persons.person_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("embedding", sa.LargeBinary, nullable=False),
        sa.Column("quality_score", sa.Float, nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()
        ),
    )
    op.create_index("ix_person_embeddings_person_id", "person_embeddings", ["person_id"])

    op.create_table(
        "user_zone_permissions",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("zone_id", sa.Integer, primary_key=True),
    )
    op.create_table(
        "user_camera_permissions",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("camera_id", sa.Integer, primary_key=True),
    )

    # ----- topology -----
    op.create_table(
        "cameras",
        sa.Column("camera_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("rtsp_url", sa.String(500), nullable=False),
        sa.Column("worker_group", sa.String(1), nullable=False),
        sa.Column("homography_matrix", sa.Text, nullable=True),
        sa.Column("fov_polygon", sa.Text, nullable=True),
        sa.Column("resolution_w", sa.Integer, nullable=False),
        sa.Column("resolution_h", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        # v2 §B + §L
        sa.Column(
            "capability_tier", sa.String(10), nullable=False, server_default=sa.text("'FULL'")
        ),
        sa.Column("profile_data", sa.Text, nullable=True),
        sa.Column("profiled_at", sa.DateTime, nullable=True),
        sa.Column("model_overrides", sa.Text, nullable=True),
        sa.CheckConstraint(
            "capability_tier IN ('FULL', 'MID', 'LOW')", name="chk_camera_tier"
        ),
    )

    op.create_table(
        "zones",
        sa.Column("zone_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("polygon", sa.Text, nullable=False),
        sa.Column("max_capacity", sa.Integer, nullable=True),
        sa.Column(
            "is_restricted", sa.Boolean, nullable=False, server_default=sa.text("0")
        ),
        sa.Column("adjacent_zone_ids", sa.Text, nullable=True),
        sa.Column("color_hex", sa.String(7), nullable=False),
        # v2 §C
        sa.Column("allowed_hours", sa.Text, nullable=True),
        sa.Column(
            "loiter_threshold_s", sa.Integer, nullable=False, server_default=sa.text("180")
        ),
    )

    # ----- tracking -----
    op.create_table(
        "tracking_events",
        sa.Column("event_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("global_track_id", sa.String(36), nullable=True),
        sa.Column("person_id", sa.Integer, sa.ForeignKey("persons.person_id"), nullable=True),
        sa.Column(
            "camera_id", sa.Integer, sa.ForeignKey("cameras.camera_id"), nullable=False
        ),
        sa.Column("zone_id", sa.Integer, nullable=True),
        sa.Column("local_track_id", sa.Integer, nullable=False),
        sa.Column("bbox_x1", sa.Integer, nullable=False),
        sa.Column("bbox_y1", sa.Integer, nullable=False),
        sa.Column("bbox_x2", sa.Integer, nullable=False),
        sa.Column("bbox_y2", sa.Integer, nullable=False),
        sa.Column("floor_x", sa.Float, nullable=True),
        sa.Column("floor_y", sa.Float, nullable=True),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column(
            "event_ts", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.UniqueConstraint(
            "camera_id", "local_track_id", "event_ts", name="uq_tracking_idem"
        ),
    )
    op.create_index("ix_tracking_events_global_track_id", "tracking_events", ["global_track_id"])
    op.create_index("ix_tracking_events_person_id", "tracking_events", ["person_id"])
    op.create_index("ix_tracking_events_camera_id", "tracking_events", ["camera_id"])
    op.create_index("ix_tracking_events_event_ts", "tracking_events", ["event_ts"])

    op.create_table(
        "reid_matches",
        sa.Column("match_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("global_track_id", sa.String(36), nullable=False),
        sa.Column(
            "person_id", sa.Integer, sa.ForeignKey("persons.person_id"), nullable=False
        ),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("match_source", sa.String(20), nullable=False),
        sa.Column("from_camera_id", sa.Integer, sa.ForeignKey("cameras.camera_id"), nullable=True),
        sa.Column("to_camera_id", sa.Integer, sa.ForeignKey("cameras.camera_id"), nullable=True),
        sa.Column(
            "matched_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()
        ),
    )
    op.create_index("ix_reid_global_track", "reid_matches", ["global_track_id"])
    op.create_index("ix_reid_person", "reid_matches", ["person_id"])

    op.create_table(
        "zone_presence",
        sa.Column("presence_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("zone_id", sa.Integer, sa.ForeignKey("zones.zone_id"), nullable=False),
        sa.Column("global_track_id", sa.String(36), nullable=False),
        sa.Column("person_id", sa.Integer, sa.ForeignKey("persons.person_id"), nullable=True),
        sa.Column("entered_at", sa.DateTime, nullable=False),
        sa.Column("exited_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_zone_presence_zone_id", "zone_presence", ["zone_id"])
    op.create_index(
        "ix_zone_presence_global_track", "zone_presence", ["global_track_id"]
    )

    # ----- maintenance windows (must come BEFORE alerts because alerts FK to it) -----
    op.create_table(
        "maintenance_windows",
        sa.Column("window_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("scope_type", sa.String(20), nullable=False),
        sa.Column("scope_id", sa.Integer, nullable=False),
        sa.Column("schedule_type", sa.String(20), nullable=False),
        sa.Column("starts_at", sa.DateTime, nullable=True),
        sa.Column("ends_at", sa.DateTime, nullable=True),
        sa.Column("cron_expr", sa.String(100), nullable=True),
        sa.Column("duration_minutes", sa.Integer, nullable=True),
        sa.Column("suppress_alert_types", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.CheckConstraint("scope_type IN ('CAMERA', 'ZONE')", name="chk_mw_scope"),
        sa.CheckConstraint(
            "schedule_type IN ('ONE_TIME', 'RECURRING')", name="chk_mw_sched"
        ),
        sa.CheckConstraint(
            "schedule_type <> 'ONE_TIME' OR (starts_at IS NOT NULL AND ends_at IS NOT NULL)",
            name="chk_mw_one_time",
        ),
        sa.CheckConstraint(
            "schedule_type <> 'RECURRING' OR (cron_expr IS NOT NULL AND duration_minutes IS NOT NULL)",
            name="chk_mw_recurring",
        ),
    )

    # ----- alerts -----
    op.create_table(
        "alerts",
        sa.Column("alert_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("alert_type", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("person_id", sa.Integer, sa.ForeignKey("persons.person_id"), nullable=True),
        sa.Column("global_track_id", sa.String(36), nullable=True),
        sa.Column("camera_id", sa.Integer, sa.ForeignKey("cameras.camera_id"), nullable=True),
        sa.Column("zone_id", sa.Integer, nullable=True),
        sa.Column("triggered_at", sa.DateTime, nullable=False),
        sa.Column("acknowledged_at", sa.DateTime, nullable=True),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("acknowledged_by", sa.Integer, sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("snapshot_path", sa.String(500), nullable=True),
        sa.Column(
            "suppressed_by_window_id",
            sa.Integer,
            sa.ForeignKey("maintenance_windows.window_id"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "state IN ('active', 'acknowledged', 'resolved', 'suppressed')",
            name="chk_alert_state",
        ),
    )
    op.create_index("ix_alerts_alert_type", "alerts", ["alert_type"])
    op.create_index("ix_alerts_triggered_at", "alerts", ["triggered_at"])

    # ----- alert dispatcher (v2 §E) -----
    op.create_table(
        "alert_routing",
        sa.Column("routing_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("alert_type", sa.String(30), nullable=True),
        sa.Column("severity", sa.String(10), nullable=True),
        sa.Column("zone_id", sa.Integer, nullable=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("target", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.CheckConstraint(
            "channel IN ('EMAIL','SLACK','TELEGRAM','WEBHOOK','WEBSOCKET')",
            name="chk_routing_channel",
        ),
    )

    op.create_table(
        "alert_dispatches",
        sa.Column("dispatch_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("alert_id", sa.Integer, sa.ForeignKey("alerts.alert_id"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("target", sa.String(500), nullable=False),
        sa.Column("attempt_n", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column(
            "dispatched_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("success", sa.Boolean, nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("response_code", sa.Integer, nullable=True),
    )
    op.create_index("ix_dispatches_alert", "alert_dispatches", ["alert_id"])

    # ----- anomaly registry (v2 §C) -----
    op.create_table(
        "anomaly_detectors",
        sa.Column("detector_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("alert_type", sa.String(30), nullable=False, unique=True),
        sa.Column("class_path", sa.String(200), nullable=False),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("config_json", sa.Text, nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column(
            "created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()
        ),
        sa.Column(
            "updated_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()
        ),
    )

    # ----- forensic CLIP (v2 §F.2) -----
    op.create_table(
        "person_clip_embeddings",
        sa.Column("clip_emb_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("global_track_id", sa.String(36), nullable=False),
        sa.Column("camera_id", sa.Integer, sa.ForeignKey("cameras.camera_id"), nullable=False),
        sa.Column("event_ts", sa.DateTime, nullable=False),
        sa.Column("embedding", sa.LargeBinary, nullable=False),
        sa.Column("snapshot_path", sa.String(500), nullable=False),
    )
    op.create_index("ix_clip_global_track", "person_clip_embeddings", ["global_track_id"])
    op.create_index("ix_clip_event_ts", "person_clip_embeddings", ["event_ts"])

    # ----- audit log (v2 §F.3) -----
    op.create_table(
        "audit_log",
        sa.Column("audit_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor_user_id", sa.Integer, sa.ForeignKey("users.user_id"), nullable=True),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.String(50), nullable=True),
        sa.Column("payload", sa.Text, nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column(
            "event_ts", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()
        ),
    )
    op.create_index("ix_audit_event_ts", "audit_log", ["event_ts"])
    op.create_index("ix_audit_target", "audit_log", ["target_type", "target_id", "event_ts"])

    # PostgreSQL declarative partitioning for tracking_events is added in a
    # Phase 5 migration once query patterns are observable (PARTITION BY RANGE (event_ts)).


def downgrade() -> None:

    op.drop_index("ix_audit_target", table_name="audit_log")
    op.drop_index("ix_audit_event_ts", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_clip_event_ts", table_name="person_clip_embeddings")
    op.drop_index("ix_clip_global_track", table_name="person_clip_embeddings")
    op.drop_table("person_clip_embeddings")

    op.drop_table("anomaly_detectors")

    op.drop_index("ix_dispatches_alert", table_name="alert_dispatches")
    op.drop_table("alert_dispatches")
    op.drop_table("alert_routing")

    op.drop_index("ix_alerts_triggered_at", table_name="alerts")
    op.drop_index("ix_alerts_alert_type", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("maintenance_windows")

    op.drop_index("ix_zone_presence_global_track", table_name="zone_presence")
    op.drop_index("ix_zone_presence_zone_id", table_name="zone_presence")
    op.drop_table("zone_presence")

    op.drop_index("ix_reid_person", table_name="reid_matches")
    op.drop_index("ix_reid_global_track", table_name="reid_matches")
    op.drop_table("reid_matches")

    op.drop_index("ix_tracking_events_event_ts", table_name="tracking_events")
    op.drop_index("ix_tracking_events_camera_id", table_name="tracking_events")
    op.drop_index("ix_tracking_events_person_id", table_name="tracking_events")
    op.drop_index("ix_tracking_events_global_track_id", table_name="tracking_events")
    op.drop_table("tracking_events")

    op.drop_table("zones")
    op.drop_table("cameras")

    op.drop_table("user_camera_permissions")
    op.drop_table("user_zone_permissions")

    op.drop_index("ix_person_embeddings_person_id", table_name="person_embeddings")
    op.drop_table("person_embeddings")

    op.drop_index("ix_persons_employee_id", table_name="persons")
    op.drop_table("persons")
    op.drop_table("users")
```

- [x] **Step 13.5: Verify migration is detected**

```powershell
$env:VMS_DB_URL="postgresql://vms:vms@localhost:5434/vms_test"
$env:VMS_JWT_SECRET="dev-secret"
alembic current
```
Expected: revision `0001 (head)` (conftest already ran `upgrade head`).

- [x] **Step 13.6: Apply the migration against PostgreSQL Docker**

```powershell
alembic upgrade head
alembic current
```
Expected: `0001 (head)`

- [x] **Step 13.7: Roll back**

```powershell
alembic downgrade base
alembic current
```
Expected: `(empty)`

- [x] **Step 13.8: Round-trip test — `tests/test_migration.py`**

```python
"""Tests for Alembic migration: upgrade head + downgrade base on PostgreSQL."""
from __future__ import annotations

from sqlalchemy import inspect

from alembic import command
from alembic.config import Config
from vms.db.session import engine


def _alembic_cfg() -> Config:
    return Config("alembic.ini")


def test_upgrade_creates_all_tables() -> None:
    command.upgrade(_alembic_cfg(), "head")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {
        "cameras", "zones", "users", "user_camera_permissions",
        "persons", "person_embeddings", "maintenance_windows",
        "alerts", "alert_routing", "alert_dispatches",
        "tracking_events", "reid_matches", "zone_presence",
        "anomaly_detectors", "person_clip_embeddings",
        "model_registry", "audit_log",
    }
    missing = expected - tables
    assert not missing, f"Tables missing after upgrade: {missing}"


def test_downgrade_removes_all_tables() -> None:
    command.upgrade(_alembic_cfg(), "head")
    command.downgrade(_alembic_cfg(), "base")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    assert not tables, f"Tables still present after downgrade: {tables}"
```

- [ ] **Step 13.9: Run the migration test**

```powershell
pytest tests/test_migration.py -v
```
Expected: 2 passed.

- [ ] **Step 13.10: Final lint + commit**

```powershell
black alembic/ tests/test_migration.py
ruff check alembic/ tests/test_migration.py
git add alembic.ini alembic/ tests/test_migration.py
git commit -m "feat(db): alembic env + initial migration for full v2 schema"
```

---

## Task 14: ~~MSSQL integration test~~ — superseded

> **Superseded.** The database is PostgreSQL + pgvector exclusively. There is no MSSQL target. The equivalent validation is `pytest tests/test_migration.py -v` against the Docker container, which is already covered in Task 13.
>
> `tracking_events` monthly partitioning will be implemented via PostgreSQL declarative partitioning (`PARTITION BY RANGE (event_ts)`) in a Phase 5 migration, not via MSSQL partition functions.

---

## Wrap-up

- [ ] **Run the entire test suite + coverage one last time**

```powershell
pytest --cov=vms --cov-report=term-missing
```
Expected: ~32 tests pass, package coverage ≥ 85%.

- [ ] **Diff summary**

```powershell
git log --oneline 2026-04-23-phase1-foundation..HEAD -- vms/ tests/ alembic/
```

- [ ] **Final commit if any local-only files were left dirty**

```powershell
git status --short
```
Expected: only the untracked legacy prototype files remain (main.py, face_detection.py, etc.). Those are removed in Phase 1B when ingestion + inference workers replace them.

---

## What this plan delivers

After all 14 tasks:

- `vms/` package importable (`import vms` returns version)
- `vms.config.Settings` reads env-var config with the v2 thresholds and pipeline tuning
- `vms.db.session` exposes a configured engine, declarative `Base`, `SessionLocal`, and FastAPI `get_db` dependency
- `vms.db.models` declares 17 ORM models — all v1 + all v2 tables — with check constraints and indexes
- `vms.db.audit.write_audit_event` writes hash-chain-linked rows to `audit_log`
- Alembic migration `0001_initial_schema.py` applies cleanly to PostgreSQL 16 + pgvector (clean DDL, no dialect branching, `Vector(512)` embeddings, `BIGSERIAL` high-volume PKs)
- 57 passing tests, covering `vms/db` and `vms/config` modules
- Round-trip migration test proves up + down work end-to-end

## What this plan deliberately does NOT deliver

- Ingestion worker, inference engine, FAISS index, anomaly detectors, alert dispatcher, camera profiler, FastAPI routes, frontend — all in subsequent plans.
- Seed data (users, anomaly_detectors initial rows) — written in Phase 1B once we have the matching Python classes.
- Production-grade index strategy beyond the foreign keys + spec-mandated indexes — additional indexes are added in Phase 5 hardening when query patterns are observable.

---

**Next plan:** `2026-05-02-vms-v2-phase1b-ingestion-and-inference.md` — Redis Streams, shared memory, ingestion worker, SCRFD/AdaFace/YOLOv8 inference engine, ByteTrack wiring, DB writer, basic FastAPI enrolment + health endpoints.
