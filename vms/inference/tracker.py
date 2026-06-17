"""Per-camera person tracker using YOLOv8x-pose + BoT-SORT.

YOLOv8x-pose outputs person bounding boxes + 17 COCO keypoints per person.
BoT-SORT (vs ByteTrack) adds camera motion compensation via sparse optical flow,
which handles factory-floor camera vibration and is more robust under occlusion.

Keypoints are passed through in Tracklet so the InferenceEngine can gate
SCRFD+AdaFace to frames where a face is actually frontal (nose+eye confidence).
"""

from __future__ import annotations

import functools
import logging
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from vms.config import get_settings
from vms.inference.keypoints import KP_DIM, face_visible
from vms.inference.messages import Tracklet

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=8)
def _render_tracker_config(base_config: str, track_buffer: int) -> str:
    """Render base BoT-SORT YAML with config-driven track_buffer into a cached temp file."""
    with open(base_config) as fh:
        data = yaml.safe_load(fh)
    data["track_buffer"] = track_buffer
    out = Path(tempfile.gettempdir()) / f"vms_botsort_buf{track_buffer}.yaml"
    with open(out, "w") as fh:
        yaml.safe_dump(data, fh)
    return str(out)


def resolve_tracker_config() -> str:
    """Return a tracker-config path with track_buffer rendered from settings."""
    settings = get_settings()
    return _render_tracker_config(settings.botsort_config, settings.tracker_buffer_frames)


class PerCameraTracker:
    """Wraps ultralytics YOLO.track() for one camera, yielding stable local_track_id values."""

    def __init__(self, camera_id: int, model: Any) -> None:
        self.camera_id = camera_id
        self._model = model
        self._frame_counter: int = 0
        self._last_tracklets: list[Tracklet] = []

    @classmethod
    def from_path(cls, camera_id: int, model_path: str) -> PerCameraTracker:
        from ultralytics import YOLO  # type: ignore[attr-defined]  # lazy; no GPU in tests

        return cls(camera_id=camera_id, model=YOLO(model_path))

    def update(self, frame_bgr: np.ndarray[Any, Any], conf: float | None = None) -> list[Tracklet]:
        """Run pose detection + BoT-SORT tracking on one frame. Returns confirmed tracklets.

        When detector_interval_frames > 1: YOLO runs on every Nth frame; on skip frames the
        last YOLO result is returned unchanged (BoT-SORT coasting). The cascade stages
        (SCRFD, AdaFace) in InferenceEngine are exempt — they keep keypoint-gated sampling.
        """
        settings = get_settings()
        interval = settings.detector_interval_frames
        should_run = interval <= 1 or (self._frame_counter % interval) == 0
        self._frame_counter += 1

        if not should_run:
            return self._last_tracklets

        results = self._model.track(
            frame_bgr,
            conf=conf if conf is not None else settings.yolo_person_conf,
            persist=True,
            tracker=resolve_tracker_config(),
            verbose=False,
        )
        if not results:
            self._last_tracklets = []
            return []
        r = results[0]
        boxes = r.boxes
        if boxes.id is None:
            self._last_tracklets = []
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
        self._last_tracklets = tracklets
        return tracklets
