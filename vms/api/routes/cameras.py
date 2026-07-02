"""Camera CRUD, configuration, and live-stream endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from vms.api.deps import get_api_redis, get_current_user, get_db, get_stream_user, require_role
from vms.api.schemas import (
    CameraCreate,
    CameraHardwareUpdate,
    CameraOverridesUpdate,
    CameraResponse,
    CameraUpdate,
    ProfileData,
    ProfileResponse,
    ResolvedConfigResponse,
    ResolvedSettingItem,
)
from vms.db.audit import write_audit_event
from vms.db.models import Camera
from vms.db.models import User as DBUser
from vms.inference.shutter_profile import resolve_camera_config
from vms.profiler.probe import CameraProfiler
from vms.profiler.report import generate_readiness_report

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_camera_or_404(camera_id: int, db: Session) -> Camera:
    cam = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    if cam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return cam


@router.get("/cameras", response_model=list[CameraResponse])
def list_cameras(
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[Camera]:
    return db.query(Camera).order_by(Camera.camera_id).all()


@router.post("/cameras", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
def create_camera(
    body: CameraCreate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Camera:
    cam = Camera(
        name=body.name,
        rtsp_url=body.rtsp_url,
        capability_tier=body.capability_tier,
        shutter_type=body.shutter_type,
        worker_group=body.worker_group,
    )
    db.add(cam)
    db.commit()
    db.refresh(cam)
    return cam


@router.get("/cameras/{camera_id}", response_model=CameraResponse)
def get_camera(
    camera_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Camera:
    return _get_camera_or_404(camera_id, db)


@router.patch("/cameras/{camera_id}", response_model=CameraResponse)
def update_camera(
    camera_id: int,
    body: CameraUpdate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Camera:
    cam = _get_camera_or_404(camera_id, db)
    if body.name is not None:
        cam.name = body.name
    if body.rtsp_url is not None:
        cam.rtsp_url = body.rtsp_url
    if body.is_active is not None:
        cam.is_active = body.is_active
    if body.capability_tier is not None:
        cam.capability_tier = body.capability_tier
    if body.shutter_type is not None:
        cam.shutter_type = body.shutter_type
    if body.worker_group is not None:
        cam.worker_group = body.worker_group
    db.commit()
    db.refresh(cam)
    return cam


@router.patch("/cameras/{camera_id}/hardware", response_model=CameraResponse)
async def update_camera_hardware(
    camera_id: int,
    body: CameraHardwareUpdate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = require_role("super_admin"),  # noqa: B008
    redis: aioredis.Redis = Depends(get_api_redis),  # noqa: B008
) -> Camera:
    cam = _get_camera_or_404(camera_id, db)
    old_shutter = cam.shutter_type
    old_tier = cam.capability_tier
    cam.shutter_type = body.shutter_type
    if body.capability_tier is not None:
        cam.capability_tier = body.capability_tier
    try:
        await redis.publish(f"camera_config_changed:{camera_id}", "hardware")
    except Exception:
        logger.warning("camera_config_changed publish failed for camera %d", camera_id)
    db.commit()
    db.refresh(cam)
    try:
        actor_id: int | None = int(_user["sub"])
    except (ValueError, KeyError):
        actor_id = None
    if actor_id is not None and db.get(DBUser, actor_id) is None:
        actor_id = None
    write_audit_event(
        db,
        event_type="CAMERA_HARDWARE_UPDATED",
        actor_user_id=actor_id,
        payload=json.dumps(
            {
                "camera_id": camera_id,
                "from": {"shutter_type": old_shutter, "capability_tier": old_tier},
                "to": {"shutter_type": cam.shutter_type, "capability_tier": cam.capability_tier},
            }
        ),
    )
    return cam


@router.patch("/cameras/{camera_id}/overrides", response_model=CameraResponse)
async def update_camera_overrides(
    camera_id: int,
    body: CameraOverridesUpdate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    redis: aioredis.Redis = Depends(get_api_redis),  # noqa: B008
) -> Camera:
    cam = _get_camera_or_404(camera_id, db)
    old_overrides = cam.model_overrides
    merged: dict[str, Any] = {}
    if body.models:
        merged.update(body.models)
    if body.thresholds:
        merged.update(body.thresholds)
    cam.model_overrides = json.dumps(merged)
    try:
        await redis.publish(f"camera_config_changed:{camera_id}", "overrides")
    except Exception:
        logger.warning("camera_config_changed publish failed for camera %d", camera_id)
    db.commit()
    db.refresh(cam)
    try:
        overrides_actor_id: int | None = int(_user["sub"])
    except (ValueError, KeyError):
        overrides_actor_id = None
    if overrides_actor_id is not None and db.get(DBUser, overrides_actor_id) is None:
        overrides_actor_id = None
    write_audit_event(
        db,
        event_type="CAMERA_OVERRIDES_UPDATED",
        actor_user_id=overrides_actor_id,
        payload=json.dumps(
            {
                "camera_id": camera_id,
                "from": old_overrides,
                "to": cam.model_overrides,
            }
        ),
    )
    return cam


@router.post("/cameras/{camera_id}/recalibrate-required", response_model=CameraResponse)
def mark_recalibrate_required(
    camera_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Camera:
    cam = _get_camera_or_404(camera_id, db)
    cam.recalibrate_required_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(cam)
    return cam


@router.get("/cameras/{camera_id}/resolved-config", response_model=ResolvedConfigResponse)
def get_resolved_config(
    camera_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> ResolvedConfigResponse:
    cam = _get_camera_or_404(camera_id, db)
    from vms.config import get_settings

    s = get_settings()
    raw = resolve_camera_config(
        shutter_type=cam.shutter_type,
        model_overrides_json=cam.model_overrides,
        base_adaface_min_sim=s.adaface_min_sim,
        base_scrfd_conf=s.scrfd_conf,
    )
    return ResolvedConfigResponse(
        camera_id=camera_id,
        settings={k: ResolvedSettingItem(value=v.value, source=v.source) for k, v in raw.items()},
    )


@router.post("/cameras/{camera_id}/profile", response_model=ProfileResponse)
def submit_profile(
    camera_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> ProfileResponse:
    cam = _get_camera_or_404(camera_id, db)
    profiler = CameraProfiler()
    try:
        data = profiler.probe(cam.rtsp_url)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"RTSP probe failed: {exc}",
        ) from exc

    cam.profile_data = json.dumps(data.model_dump(exclude_none=False))
    cam.capability_tier = data.suggested_tier or cam.capability_tier
    cam.shutter_type = data.shutter_suggestion or cam.shutter_type
    cam.profiled_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(cam)

    return ProfileResponse(
        camera_id=cam.camera_id,
        profile_data=data,
        profiled_at=cam.profiled_at,
        capability_tier=cam.capability_tier,
        shutter_type=cam.shutter_type,
        tier_reason=data.tier_reason,
    )


@router.get("/cameras/{camera_id}/profile", response_model=ProfileResponse)
def get_profile(
    camera_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> ProfileResponse:
    cam = _get_camera_or_404(camera_id, db)
    profile_parsed: ProfileData | None = None
    if cam.profile_data:
        try:
            profile_parsed = ProfileData(**json.loads(cam.profile_data))
        except (json.JSONDecodeError, ValueError):
            profile_parsed = None
    return ProfileResponse(
        camera_id=cam.camera_id,
        profile_data=profile_parsed,
        profiled_at=cam.profiled_at,
        capability_tier=cam.capability_tier,
        shutter_type=cam.shutter_type,
        tier_reason=profile_parsed.tier_reason if profile_parsed else None,
    )


@router.get("/sites/readiness-report.pdf")
def get_site_readiness_report(
    site: str = "Plant Site",
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Response:
    cameras = db.query(Camera).order_by(Camera.camera_id).all()
    rows = []
    for cam in cameras:
        pd: ProfileData | None = None
        if cam.profile_data:
            try:
                pd = ProfileData(**json.loads(cam.profile_data))
            except (json.JSONDecodeError, ValueError):
                pd = None
        rows.append(
            {
                "camera_id": cam.camera_id,
                "name": cam.name,
                "capability_tier": cam.capability_tier,
                "shutter_type": cam.shutter_type,
                "tier_reason": pd.tier_reason if pd else None,
                "profile_data": pd,
            }
        )
    pdf_bytes = generate_readiness_report(rows, site_name=site)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="vms-site-readiness-{site}.pdf"'},
    )


# ---------------------------------------------------------------------------
# Live streaming helpers (MJPEG + snapshot)
# ---------------------------------------------------------------------------

_MJPEG_BOUNDARY = b"vmsframe"
_MJPEG_JPEG_QUALITY = 60  # percent — reduces bandwidth; fine for browser display
_MJPEG_TARGET_FPS = 15  # cap at 15fps to keep bandwidth reasonable
_SNAPSHOT_JPEG_QUALITY = 80


def _open_capture(rtsp_url: str) -> Any:
    """Open an RTSP VideoCapture; raises RuntimeError on failure. Runs in a thread."""
    import cv2  # local import — cv2 optional for deployments without streaming

    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
    if not cap.isOpened():
        raise RuntimeError("Cannot open RTSP stream for camera")
    return cap


@router.get("/cameras/{camera_id}/snapshot")
async def camera_snapshot(
    camera_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_stream_user),  # noqa: B008
) -> Response:
    """Return a single JPEG frame from the camera. Cached by the ?t= query param."""
    import cv2  # local import

    cam = _get_camera_or_404(camera_id, db)
    if not cam.rtsp_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No stream URL configured"
        )

    rtsp_url: str = cam.rtsp_url
    loop = asyncio.get_event_loop()

    def _grab_frame() -> bytes:
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        try:
            ret, frame = cap.read()
            if not ret or frame is None:
                raise RuntimeError("Empty frame")
            _, jpeg = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _SNAPSHOT_JPEG_QUALITY]
            )
            return jpeg.tobytes()
        finally:
            cap.release()

    try:
        jpeg_bytes = await loop.run_in_executor(None, _grab_frame)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return Response(
        content=jpeg_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/cameras/{camera_id}/mjpeg")
async def camera_mjpeg_stream(
    camera_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_stream_user),  # noqa: B008
) -> StreamingResponse:
    """Stream MJPEG from the camera. Display with <img src="/api/cameras/{id}/mjpeg?token=…">."""
    import cv2  # local import

    cam = _get_camera_or_404(camera_id, db)
    if not cam.rtsp_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No stream URL configured"
        )

    rtsp_url: str = cam.rtsp_url
    loop = asyncio.get_event_loop()
    min_frame_interval = 1.0 / _MJPEG_TARGET_FPS

    async def generate() -> Any:
        cap = None
        try:
            cap = await loop.run_in_executor(None, lambda: _open_capture(rtsp_url))
        except RuntimeError:
            return

        consecutive_failures = 0
        last_frame_t = 0.0
        try:
            while consecutive_failures < 30:
                ret, frame = await loop.run_in_executor(None, cap.read)
                if not ret or frame is None:
                    consecutive_failures += 1
                    await asyncio.sleep(0.2)
                    continue
                consecutive_failures = 0

                now = time.monotonic()
                gap = min_frame_interval - (now - last_frame_t)
                if gap > 0:
                    await asyncio.sleep(gap)
                last_frame_t = time.monotonic()

                success, jpeg = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _MJPEG_JPEG_QUALITY]
                )
                if not success:
                    continue

                yield (
                    b"--" + _MJPEG_BOUNDARY + b"\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
                )
        except (GeneratorExit, asyncio.CancelledError):
            pass
        finally:
            if cap is not None:
                await loop.run_in_executor(None, cap.release)

    return StreamingResponse(
        generate(),
        media_type=f"multipart/x-mixed-replace; boundary={_MJPEG_BOUNDARY.decode()}",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
