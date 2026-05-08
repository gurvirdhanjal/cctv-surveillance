"""Alembic environment — connects to VMS_DB_URL and uses vms.db.session.Base."""

from __future__ import annotations

from logging.config import fileConfig

import vms.db.models  # noqa: F401 — registers all ORM models with Base.metadata
from alembic import context
from vms.config import get_settings
from vms.db.session import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _db_url() -> str:
    return get_settings().db_url


def run_migrations_offline() -> None:
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from vms.db.session import engine as _app_engine

    # Use the app's engine so SQLite :memory: tests share the same DB connection.
    # On PostgreSQL this makes no difference — both point to the same server.
    with _app_engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
