"""FastAPI application entry point."""

from __future__ import annotations

import pathlib

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vms.api.routes import auth, health, persons
from vms.config import Settings, get_settings
from vms.db.partition_manager import ensure_future_partitions
from vms.db.session import engine


def _apply_media_mount(app: FastAPI, settings: Settings) -> None:
    """Mount /media as StaticFiles when using local storage and the dir exists."""
    if settings.storage_backend == "local" and pathlib.Path(settings.storage_local_dir).exists():
        app.mount(
            "/media",
            StaticFiles(directory=settings.storage_local_dir, html=False),
            name="media",
        )


app = FastAPI(title="VMS API", version="0.1.0")

app.include_router(auth.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(persons.router, prefix="/api")


def _call_ensure_future_partitions() -> None:
    """Create monthly tracking_events partitions for current month + 3 months ahead."""
    ensure_future_partitions(engine, months_ahead=3)


_apply_media_mount(app, get_settings())
_call_ensure_future_partitions()
