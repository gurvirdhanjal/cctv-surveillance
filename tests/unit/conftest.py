"""Conftest for unit tests — override database fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> Iterator[None]:
    """Override: skip Alembic migrations for unit tests."""
    yield


@pytest.fixture(scope="session", autouse=True)
def _ensure_partitions() -> Iterator[None]:
    """Override: skip partition setup for unit tests."""
    yield


@pytest.fixture(scope="session")
def db_engine() -> MagicMock:  # type: ignore[no-untyped-def]
    """Override: return a mock engine instead of trying to connect."""
    return MagicMock()
