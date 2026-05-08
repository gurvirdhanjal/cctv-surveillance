"""SQLAlchemy engine, declarative Base, session factory, and FastAPI dependency."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from vms.config import get_settings

_settings = get_settings()

# SQLite requires check_same_thread=False for multi-threaded test access;
# psycopg2/PostgreSQL ignores this kwarg.
engine = create_engine(
    _settings.db_url,
    pool_pre_ping=True,
    future=True,
    connect_args=({"check_same_thread": False} if _settings.db_url.startswith("sqlite") else {}),
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection: Any, _: Any) -> None:
    """Enable FK enforcement for the SQLite test backend."""
    if _settings.db_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    with SessionLocal() as session:
        yield session
