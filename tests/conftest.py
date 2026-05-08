"""Shared pytest fixtures for the VMS test suite."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

# Set defaults before any VMS module is imported during collection.
# Module-level code in session.py calls get_settings() at import time,
# so these must be present before collection starts.
os.environ.setdefault("VMS_DB_URL", "sqlite:///:memory:")
os.environ.setdefault("VMS_JWT_SECRET", "test-secret-do-not-use")
os.environ.setdefault("VMS_REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("VMS_SCRFD_MODEL", "models/scrfd_2.5g.onnx")
os.environ.setdefault("VMS_ADAFACE_MODEL", "models/adaface_ir50.onnx")
os.environ.setdefault("VMS_BYTETRACK_CONFIG", "bytetrack_custom.yaml")


@pytest.fixture()
def db_session() -> Iterator[Any]:
    """Provide a clean in-memory SQLite session with all tables created."""
    from sqlalchemy.orm import Session as SASession

    import vms.db.models  # noqa: F401 — registers all ORM models with Base.metadata
    from vms.db.session import Base, SessionLocal, engine

    Base.metadata.create_all(bind=engine)
    session: SASession
    with SessionLocal() as session:
        yield session
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _vms_env() -> Iterator[None]:
    """Provide deterministic env vars for every test."""
    with patch.dict(
        os.environ,
        {
            "VMS_DB_URL": "sqlite:///:memory:",
            "VMS_REDIS_URL": "redis://localhost:6379/0",
            "VMS_JWT_SECRET": "test-secret-do-not-use",
            "VMS_SCRFD_MODEL": "models/scrfd_2.5g.onnx",
            "VMS_ADAFACE_MODEL": "models/adaface_ir50.onnx",
            "VMS_BYTETRACK_CONFIG": "bytetrack_custom.yaml",
        },
        clear=False,
    ):
        yield
