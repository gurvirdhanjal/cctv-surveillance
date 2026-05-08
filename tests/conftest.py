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
    """Run Alembic migrations once per test session; downgrade when done."""
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield
    command.downgrade(cfg, "base")


@pytest.fixture()
def db_session() -> Iterator[Any]:
    """Each test runs inside a rolled-back transaction for full isolation."""
    import vms.db.models  # noqa: F401 — ensure all models are registered

    from vms.db.session import engine

    connection = engine.connect()
    transaction = connection.begin()
    session: SASession = SASession(
        bind=connection, join_transaction_mode="create_savepoint"
    )
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
