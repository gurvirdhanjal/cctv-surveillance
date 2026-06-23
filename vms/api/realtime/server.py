"""Socket.io AsyncServer — JWT auth, room subscriptions (§10)."""

from __future__ import annotations

import logging
from typing import Any

import socketio  # type: ignore[import-untyped]
from jose import JWTError  # type: ignore[import-untyped]

from vms.api.deps import decode_access_token
from vms.config import get_settings

logger = logging.getLogger(__name__)


def _build_cors_origins(origin_str: str) -> str | list[str]:
    if not origin_str or origin_str == "*":
        return "*"
    parts = [o.strip() for o in origin_str.split(",") if o.strip()]
    return parts if len(parts) > 1 else parts[0]


sio: socketio.AsyncServer = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=_build_cors_origins(get_settings().frontend_origin),
    logger=False,
    engineio_logger=False,
)


async def _validate_connect(auth: dict[str, Any] | None) -> dict[str, Any]:
    """Validate the connect auth payload.

    Returns the decoded JWT payload on success.
    Raises ConnectionRefusedError when token is absent or invalid.
    """
    token: str | None = (auth or {}).get("token")
    if not token:
        raise ConnectionRefusedError("authentication required")
    try:
        return decode_access_token(token)
    except JWTError as exc:
        raise ConnectionRefusedError("invalid token") from exc


@sio.event  # type: ignore[untyped-decorator]
async def connect(sid: str, environ: dict[str, Any], auth: dict[str, Any] | None = None) -> None:
    user = await _validate_connect(auth)
    await sio.save_session(sid, {"user": user})
    logger.debug("socket connected sid=%s role=%s", sid, user.get("role"))


@sio.event  # type: ignore[untyped-decorator]
async def disconnect(sid: str) -> None:
    logger.debug("socket disconnected sid=%s", sid)


@sio.event  # type: ignore[untyped-decorator]
async def subscribe_camera(sid: str, data: dict[str, Any]) -> None:
    camera_id = data.get("camera_id")
    if camera_id is not None:
        await sio.enter_room(sid, f"camera:{camera_id}")


@sio.event  # type: ignore[untyped-decorator]
async def unsubscribe_camera(sid: str, data: dict[str, Any]) -> None:
    camera_id = data.get("camera_id")
    if camera_id is not None:
        await sio.leave_room(sid, f"camera:{camera_id}")


@sio.event  # type: ignore[untyped-decorator]
async def subscribe_track(sid: str, data: dict[str, Any]) -> None:
    gid = data.get("global_track_id")
    if gid is not None:
        await sio.enter_room(sid, f"track:{gid}")
