"""Per-camera person tracker using YOLOv8x-pose + BoT-SORT.

YOLOv8x-pose outputs person bounding boxes + 17 COCO keypoints per person.
BoT-SORT (vs ByteTrack) adds camera motion compensation via sparse optical flow,
which handles factory-floor camera vibration and is more robust under occlusion.

Keypoints are passed through in Tracklet so the InferenceEngine can gate
SCRFD+AdaFace to frames where a face is actually frontal (nose+eye confidence).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from vms.config import get_settings
from vms.inference.keypoints import KP_DIM, face_visible
from vms.inference.messages import Tracklet

logger = logging.getLogger(__name__)


class PerCameraTracker:
    """Wraps ultralytics YOLO.track() for one camera, yielding stable local_track_id values."""

    def __init__(self, camera_id: int, model: Any) -> None:
        self.camera_id = camera_id
        self._model = model

    @classmethod
    def from_path(cls, camera_id: int, model_path: str) -> PerCameraTracker:
        from ultralytics import YOLO  # type: ignore[import-untyped]  # lazy; no GPU in tests

        return cls(camera_id=camera_id, model=YOLO(model_path))

    def update(self, frame_bgr: np.ndarray[Any, Any]) -> list[Tracklet]:
        """Run pose detection + BoT-SORT tracking on one frame. Returns confirmed tracklets."""
        settings = get_settings()
        results = self._model.track(
            frame_bgr,
            conf=settings.scrfd_conf,
            persist=True,
            tracker=settings.botsort_config,
            verbose=False,
        )
        if not results:
            return []
        r = results[0]
        boxes = r.boxes
        if boxes.id is None:
            return []

        has_kpts = getattr(r, "keypoints", None) is not None
        kpts_data = r.keypoints.data if has_kpts else None  # (N, 17, 3) tensor

        tracklets: list[Tracklet] = []
        for i, (bbox_arr, tid, conf) in enumerate(
            zip(boxes.xyxy, boxes.id, boxes.conf, strict=False)
        ):
            x1, y1, x2, y2 = (int(v) for v in bbox_arr)

            kpts: tuple[tuple[float, float, float], ...] = ()
            fv = False
            if kpts_data is not None and i < len(kpts_data):
                raw = kpts_data[i]  # (17, 3)
                kpts = tuple(
                    (float(raw[j, 0]), float(raw[j, 1]), float(raw[j, 2]))
                    for j in range(min(KP_DIM, raw.shape[0]))
                )
                fv = face_visible(kpts, min_conf=settings.face_kpt_min_conf)

            tracklets.append(
                Tracklet(
                    local_track_id=int(tid),
                    camera_id=self.camera_id,
                    bbox=(x1, y1, x2, y2),
                    confidence=float(conf),
                    keypoints=kpts,
                    face_visible=fv,
                )
            )
        return tracklets
