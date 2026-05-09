"""Ingestion worker: camera → shared memory → Redis Stream."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import cv2
import numpy as np
import redis.asyncio as aioredis

from vms.ingestion.messages import FramePointer
from vms.ingestion.shm import SHMSlot
from vms.redis_client import stream_add

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    camera_id: int
    rtsp_url: str
    worker_group: int
    width: int = 1920
    height: int = 1080


class IngestionWorker:
    """Reads frames from one camera, writes to SHM, publishes FramePointer to Redis."""

    def __init__(self, camera: CameraConfig, redis_client: aioredis.Redis) -> None:
        self._camera = camera
        self._redis = redis_client
        self._seq_id: int = 0
        self._running: bool = False
        self._slot: SHMSlot | None = None

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

    async def _capture_loop(self) -> None:
        cap = cv2.VideoCapture(self._camera.rtsp_url)
        stream_name = f"frames:group{self._camera.worker_group}"
        try:
            while self._running:
                ret, frame = cap.read()
                if not ret:
                    logger.warning("camera_id=%d frame read failed", self._camera.camera_id)
                    await asyncio.sleep(0.1)
                    continue
                frame_np = np.asarray(frame, dtype=np.uint8)
                if frame_np.shape[:2] != (self._camera.height, self._camera.width):
                    frame_np = np.asarray(
                        cv2.resize(frame_np, (self._camera.width, self._camera.height)),
                        dtype=np.uint8,
                    )
                assert self._slot is not None
                ts_ms = self._slot.write(frame_np, self._seq_id)
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
