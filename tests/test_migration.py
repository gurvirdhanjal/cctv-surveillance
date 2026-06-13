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
        "cameras",
        "zones",
        "users",
        "user_camera_permissions",
        "persons",
        "person_embeddings",
        "maintenance_windows",
        "alerts",
        "alert_routing",
        "alert_dispatches",
        "tracking_events",
        "reid_matches",
        "zone_presence",
        "anomaly_detectors",
        "person_clip_embeddings",
        "model_registry",
        "audit_log",
    }
    missing = expected - tables
    assert not missing, f"Tables missing after upgrade: {missing}"


def test_downgrade_removes_all_tables() -> None:
    command.upgrade(_alembic_cfg(), "head")
    command.downgrade(_alembic_cfg(), "base")

    inspector = inspect(engine)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    assert not tables, f"Tables still present after downgrade: {tables}"
