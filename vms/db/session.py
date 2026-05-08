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
