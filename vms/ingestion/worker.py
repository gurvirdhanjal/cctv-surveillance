"""Ingestion worker: camera → shared memory → Redis Stream."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np
import redis.asyncio as aioredis
from sqlalchemy.orm import Session

from vms.config import get_settings
from vms.ingestion.messages import FramePointer
from vms.ingestion.shm import SHMSlot
from vms.redis_client import stream_add

logger = logging.getLogger(__name__)

# Default backoff steps in seconds — overridden at runtime via rtsp_backoff_delays_ms.
_BACKOFF_DELAYS = (1, 2, 4, 8, 16, 32)


@dataclass
class CameraConfig:
    camera_id: int
    rtsp_url: str
    worker_group: int
    width: int = 1920
    height: int = 1080


class IngestionWorker:
    """Reads frames from one camera, writes to SHM, publishes FramePointer to Redis."""

    def __init__(
        self,
        camera: CameraConfig,
        redis_client: aioredis.Redis,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self._camera = camera
        self._redis = redis_client
        self._session_factory = session_factory
        self._seq_id: int = 0
        self._running: bool = False
        self._slot: SHMSlot | None = None
        self._consecutive_failures: int = 0

    async def start(self) -> None:
        shm_name = f"vms_cam_{self._camera.camera_id}"
        self._slot = SHMSlot.create(shm_name, self._camera.width, self._camera.height)
        self._running = True
        try:
            await self._capture_loop()
        finally:
            if self._slot:
                self._slot.close()
                self._slot.unlink()

    async def stop(self) -> None:
        self._running = False

    async def _stream_add_with_retry(
        self,
        stream_name: str,
        fields: dict[str, str],
    ) -> None:
        settings = get_settings()
        max_attempts = settings.redis_stream_retry_attempts
        delay_s = settings.redis_stream_retry_delay_ms / 1000.0
        for attempt in range(1, max_attempts + 1):
            try:
                await stream_add(self._redis, stream_name, fields)
                return
            except Exception:
                if attempt == max_attempts:
                    logger.exception(
                        "camera_id=%d stream_add failed after %d attempts; dropping frame seq=%d",
                        self._camera.camera_id,
                        max_attempts,
                        self._seq_id,
                    )
                    return
                logger.warning(
                    "camera_id=%d stream_add attempt %d/%d failed; retrying in %.1fs",
                    self._camera.camera_id,
                    attempt,
                    max_attempts,
                    delay_s,
                )
                await asyncio.sleep(delay_s)

    async def _mark_camera_inactive(self) -> None:
        if self._session_factory is None:
            return
        session = self._session_factory()
        try:
            from vms.db.models import Camera

            cam = session.get(Camera, self._camera.camera_id)
            if cam is not None:
                cam.is_active = False
                session.commit()
        except Exception:
            logger.exception("camera_id=%d failed to mark camera inactive", self._camera.camera_id)
        finally:
            session.close()

    async def _capture_loop(self) -> None:
        cap = cv2.VideoCapture(self._camera.rtsp_url)
        stream_name = f"frames:group{self._camera.worker_group}"
        settings = get_settings()
        failure_threshold = settings.rtsp_failure_threshold
        backoff_delays = [d / 1000.0 for d in settings.rtsp_backoff_delays_ms]
        try:
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    self._consecutive_failures += 1
                    delay = backoff_delays[
                        min(self._consecutive_failures - 1, len(backoff_delays) - 1)
                    ]
                    logger.warning(
                        "camera_id=%d frame read failed (failures=%d, backoff=%ds)",
                        self._camera.camera_id,
                        self._consecutive_failures,
                        delay,
                    )
                    if self._consecutive_failures >= failure_threshold:
                        logger.error(
                            "camera_id=%d exceeded failure threshold (%d), marking inactive",
                            self._camera.camera_id,
                            failure_threshold,
                        )
                        await self._mark_camera_inactive()
                        self._running = False
                        break
                    await asyncio.sleep(delay)
                    continue

                self._consecutive_failures = 0
                frame_np = np.asarray(frame, dtype=np.uint8)
                if frame_np.shape[:2] != (self._camera.height, self._camera.width):
                    frame_np = np.asarray(
                        cv2.resize(frame_np, (self._camera.width, self._camera.height)),
                        dtype=np.uint8,
                    )
                if self._slot is None:
                    raise RuntimeError(
                        "SHMSlot not initialised — call start() before _capture_loop()"
                    )
                ts_ms = self._slot.write(frame_np, self._seq_id)  # type: ignore[arg-type]  # np.asarray returns generic shape; frame is always HxWx3 BGR at runtime
                pointer = FramePointer(
                    cam_id=self._camera.camera_id,
                    shm_name=self._slot.name,
                    seq_id=self._seq_id,
                    timestamp_ms=ts_ms,
                    width=self._camera.width,
                    height=self._camera.height,
                )
                await stream_add(self._redis, stream_name, pointer.to_redis_fields())
                self._seq_id += 1
                await asyncio.sleep(0)  # yield to event loop
        finally:
            cap.release()
