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
