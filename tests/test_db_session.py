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
    import contextlib

    with contextlib.suppress(StopIteration):
        next(gen)
