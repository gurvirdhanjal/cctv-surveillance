"""FastAPI application entry point."""

from __future__ import annotations

import pathlib

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vms.api.routes import auth, health, persons
from vms.config import Settings, get_settings


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

_apply_media_mount(app, get_settings())
