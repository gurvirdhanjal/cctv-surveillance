"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
import pathlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from vms.api.routes import (
    alerts,
    anomaly_detectors,
    audit,
    auth,
    cameras,
    health,
    maintenance,
    persons,
    routing,
    state,
)
from vms.config import Settings, get_settings
from vms.db.partition_manager import ensure_future_partitions
from vms.db.session import SessionLocal, engine

logger = logging.getLogger(__name__)


def _apply_media_mount(app: FastAPI, settings: Settings) -> None:
    """Mount /media as StaticFiles when using local storage and the dir exists."""
    if settings.storage_backend == "local" and pathlib.Path(settings.storage_local_dir).exists():
        app.mount(
            "/media",
            StaticFiles(directory=settings.storage_local_dir, html=False),
            name="media",
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from vms.api.deps import get_api_redis
    from vms.dispatcher.worker import AlertDispatcher

    redis = get_api_redis()
    dispatcher = AlertDispatcher.from_settings(
        redis=redis,
        db_session_factory=SessionLocal,
    )
    task = asyncio.create_task(dispatcher.run(), name="alert-dispatcher")
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("AlertDispatcher raised unexpected error during shutdown")


app = FastAPI(title="VMS API", version="0.2.0", lifespan=lifespan)

app.include_router(auth.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(persons.router, prefix="/api")
app.include_router(state.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(anomaly_detectors.router, prefix="/api")
app.include_router(maintenance.router, prefix="/api")
app.include_router(cameras.router, prefix="/api")
app.include_router(routing.router, prefix="/api")

# Prometheus metrics endpoint (standard /metrics path, no /api prefix)
app.mount("/metrics", make_asgi_app())


def _call_ensure_future_partitions() -> None:
    """Create monthly tracking_events partitions for current month + 3 months ahead."""
    ensure_future_partitions(engine, months_ahead=3)


_apply_media_mount(app, get_settings())
_call_ensure_future_partitions()
