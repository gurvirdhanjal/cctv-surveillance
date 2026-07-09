"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import logging
import pathlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import socketio as _socketio  # type: ignore[import-untyped]
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app
from sqlalchemy.exc import IntegrityError as SAIntegrityError

from vms.api.realtime.bridge import run_bridge
from vms.api.realtime.server import sio
from vms.api.routes import (
    alerts,
    analytics,
    anomaly_detectors,
    audit,
    auth,
    cameras,
    forensic,
    health,
    maintenance,
    persons,
    routing,
    state,
    system,
    users,
    zones,
)
from vms.config import Settings, get_settings
from vms.db.partition_manager import ensure_future_partitions
from vms.db.session import SessionLocal, engine

logger = logging.getLogger(__name__)


def _apply_spa_mount(
    app: FastAPI,
    settings: Settings,
    *,
    dist_path: pathlib.Path | None = None,
) -> None:
    """Mount frontend/dist/ as a history-mode SPA.

    All requests that do not match an existing route return index.html so
    client-side routing (React Router) resolves deep links correctly.
    The /assets sub-directory is mounted separately so Vite's hashed bundles
    get efficient static-file serving.

    The mount is registered last — API routers and other mounts added before
    this call take precedence over the catch-all.
    """
    if not settings.serve_frontend:
        return
    dist = dist_path or (pathlib.Path(__file__).parent.parent.parent / "frontend" / "dist")
    if not dist.exists():
        logger.warning("VMS_SERVE_FRONTEND=true but frontend/dist/ not found — SPA mount skipped")
        return
    assets_dir = dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="spa-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _serve_spa(full_path: str) -> Response:
        candidate = dist / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(dist / "index.html"))


def _apply_media_mount(app: FastAPI, settings: Settings) -> None:
    """Mount /media as StaticFiles when using local storage and the dir exists."""
    if settings.storage_backend == "local" and pathlib.Path(settings.storage_local_dir).exists():
        app.mount(
            "/media",
            StaticFiles(directory=settings.storage_local_dir, html=False),
            name="media",
        )


def _call_ensure_future_partitions() -> None:
    """Thin wrapper so tests can assert partition creation is triggered on startup."""
    ensure_future_partitions(engine, months_ahead=3)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from vms.api.deps import get_api_redis
    from vms.dispatcher.worker import AlertDispatcher

    try:
        _call_ensure_future_partitions()
    except Exception:
        logger.warning(
            "Could not create tracking_events partitions on startup — DB may not be ready yet",
            exc_info=True,
        )

    redis = get_api_redis()
    dispatcher = AlertDispatcher.from_settings(
        redis=redis,
        db_session_factory=SessionLocal,
    )
    task = asyncio.create_task(dispatcher.run(), name="alert-dispatcher")
    bridge_task = asyncio.create_task(run_bridge(get_settings().redis_url), name="realtime-bridge")
    try:
        yield
    finally:
        for t in (task, bridge_task):
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Background task raised unexpected error during shutdown")
        try:
            await redis.aclose()
        except Exception:
            logger.exception("Error closing Redis connection during shutdown")


app = FastAPI(title="VMS API", version="0.2.0", lifespan=lifespan)


@app.exception_handler(SAIntegrityError)
async def integrity_error_handler(request: Request, exc: SAIntegrityError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "Database constraint violation"})


app.include_router(auth.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(persons.router, prefix="/api")
app.include_router(zones.router, prefix="/api")
app.include_router(state.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(anomaly_detectors.router, prefix="/api")
app.include_router(maintenance.router, prefix="/api")
app.include_router(cameras.router, prefix="/api")
app.include_router(routing.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(forensic.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(users.router, prefix="/api")

# Prometheus metrics endpoint (standard /metrics path, no /api prefix)
app.mount("/metrics", make_asgi_app())


_apply_media_mount(app, get_settings())
_apply_spa_mount(app, get_settings())

# Combined ASGI app: socket.io intercepts /socket.io/* paths; all others go to FastAPI.
# Run this with: uvicorn vms.api.main:socket_app
socket_app: Any = _socketio.ASGIApp(sio, other_asgi_app=app)
