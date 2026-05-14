"""Per-camera person tracker using ultralytics YOLOv8n + ByteTrack."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from vms.config import get_settings
from vms.inference.messages import Tracklet

logger = logging.getLogger(__name__)


class PerCameraTracker:
    """Wraps ultralytics YOLO.track() for one camera, yielding stable local_track_id values."""

    def __init__(self, camera_id: int, model: Any) -> None:
        self.camera_id = camera_id
        self._model = model

    @classmethod
    def from_path(cls, camera_id: int, model_path: str) -> PerCameraTracker:
        from ultralytics import (
            YOLO,  # type: ignore[attr-defined]  # lazy import; no GPU needed in tests
        )

        return cls(camera_id=camera_id, model=YOLO(model_path))

    def update(self, frame_bgr: np.ndarray[Any, Any]) -> list[Tracklet]:
        """Run detection + tracking on one frame. Returns confirmed tracklets."""
        settings = get_settings()
        results = self._model.track(
            frame_bgr,
            conf=settings.scrfd_conf,
            persist=True,
            tracker=settings.bytetrack_config,
            verbose=False,
        )
        if not results:
            return []
        boxes = results[0].boxes
        if boxes.id is None:
            return []

        tracklets: list[Tracklet] = []
        for bbox_arr, tid, conf in zip(boxes.xyxy, boxes.id, boxes.conf, strict=False):
            x1, y1, x2, y2 = (int(v) for v in bbox_arr)
            tracklets.append(
                Tracklet(
                    local_track_id=int(tid),
                    camera_id=self.camera_id,
                    bbox=(x1, y1, x2, y2),
                    confidence=float(conf),
                )
            )
        return tracklets
