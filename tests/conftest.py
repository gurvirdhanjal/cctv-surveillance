"""Shared pytest fixtures for the VMS test suite.

Test database: PostgreSQL 16 + pgvector, running in Docker.
Start with:
    docker run -d --name vms-test-db \\
        -e POSTGRES_PASSWORD=vms -e POSTGRES_DB=vms_test -e POSTGRES_USER=vms \\
        -p 5434:5432 pgvector/pgvector:pg16
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session as SASession

# Set defaults before any VMS module is imported during collection.
# Module-level code in session.py calls get_settings() at import time.
os.environ.setdefault("VMS_DB_URL", "postgresql://vms:vms@localhost:5434/vms_test")
os.environ.setdefault("VMS_JWT_SECRET", "test-secret-do-not-use")
os.environ.setdefault("VMS_REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("VMS_SCRFD_MODEL", "models/scrfd_2.5g.onnx")
os.environ.setdefault("VMS_ADAFACE_MODEL", "models/adaface_ir50.onnx")
os.environ.setdefault("VMS_BYTETRACK_CONFIG", "bytetrack_custom.yaml")


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> Iterator[None]:
    """Run Alembic migrations once per test session; downgrade when done.

    Downgrades first so that a previous session that crashed mid-run (e.g. OOM)
    does not leave stale rows that cause unique-constraint failures in API tests.
    """
    try:
        import contextlib

        from alembic.config import Config

        from alembic import command

        cfg = Config("alembic.ini")
        # Downgrade first: idempotent — safe even if no schema exists yet
        with contextlib.suppress(Exception):
            command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
        yield
        command.downgrade(cfg, "base")
    except ImportError:
        # Alembic not available; skip schema setup
        yield


@pytest.fixture(scope="session")
def db_engine():  # type: ignore[no-untyped-def]
    """Return the SQLAlchemy engine bound to the test database."""
    from vms.db.session import engine as _engine

    return _engine


@pytest.fixture(scope="session", autouse=True)
def _ensure_partitions(_create_schema: None, db_engine) -> None:  # type: ignore[no-untyped-def]
    """Ensure current-month tracking_events partition exists for integration tests."""
    from vms.db.partition_manager import ensure_future_partitions

    ensure_future_partitions(db_engine, months_ahead=1)


@pytest.fixture()
def db_session() -> Iterator[Any]:
    """Each test runs inside a rolled-back transaction for full isolation."""
    import vms.db.models  # noqa: F401 — ensure all models are registered
    from vms.db.session import engine

    connection = engine.connect()
    transaction = connection.begin()
    session: SASession = SASession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def _vms_env() -> Iterator[None]:
    """Pin env vars for every test (prevents leakage from real environment)."""
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


@pytest.fixture(autouse=True)
def _reset_api_redis() -> Iterator[None]:
    """Reset the process-level Redis singleton between tests.

    The singleton caches a client bound to a specific event loop. pytest-asyncio
    creates a new loop per test, so a stale client would fail on teardown with
    'Event loop is closed'. Resetting it forces a fresh client each test.
    """
    import vms.api.deps as deps

    deps._api_redis = None
    yield
    if deps._api_redis is not None:
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.run_until_complete(deps._api_redis.aclose())
        except Exception:
            pass
    deps._api_redis = None
