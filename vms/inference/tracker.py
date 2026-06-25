"""Per-camera person tracker using YOLO26m-pose + BoT-SORT.

YOLO26m-pose outputs person bounding boxes + 17 COCO keypoints per person.
BoT-SORT (vs ByteTrack) adds camera motion compensation via sparse optical flow,
which handles factory-floor camera vibration and is more robust under occlusion.

Keypoints are passed through in Tracklet so the InferenceEngine can gate
SCRFD+AdaFace to frames where a face is actually frontal (nose+eye confidence).

Three-layer YOLO throttling (§6.0.25 + §6.0.3):
  1. Motion gate — skip YOLO entirely on static frames (frame diff or MOG2).
  2. Fixed interval — run YOLO every Nth frame; tracker coasts on skip frames.
  3. Adaptive interval — per-camera state machine that raises the interval during
     idle periods and resets it to 1 the moment a new person is detected.

All three layers are independently configurable and compose additively.
Cascade stages (SCRFD, AdaFace) in InferenceEngine are exempt from all throttling.
"""

from __future__ import annotations

import functools
import logging
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

from vms.config import get_settings
from vms.inference.keypoints import KP_DIM, face_visible
from vms.inference.messages import Tracklet

logger = logging.getLogger(__name__)

# Pixel delta threshold for frame_diff mode (0-255). Pixels with a grayscale
# delta below this are treated as unchanged. 25 is a robust default for indoor
# factory lighting — insensitive to JPEG compression noise but catches real motion.
_FRAME_DIFF_PIXEL_THRESHOLD = 25


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
        # fixed / adaptive interval state
        self._frame_counter: int = 0
        self._last_tracklets: list[Tracklet] = []
        # adaptive interval state (§6.0.3)
        self._adapt_interval: int = 1
        self._no_new_detect_count: int = 0
        self._prev_track_ids: set[int] = set()
        # motion gate state (§6.0.25)
        self._prev_frame_gray: np.ndarray[Any, Any] | None = None
        self._static_count: int = 0
        self._mog2: Any = None  # cv2.BackgroundSubtractorMOG2, created lazily
        self._last_motion_mask: np.ndarray[Any, Any] | None = None

    @classmethod
    def from_path(cls, camera_id: int, model_path: str) -> PerCameraTracker:
        from ultralytics import YOLO  # type: ignore[attr-defined]  # lazy; no GPU in tests

        return cls(camera_id=camera_id, model=YOLO(model_path))

    # ------------------------------------------------------------------
    # Motion gate (§6.0.25)
    # ------------------------------------------------------------------

    def _motion_gate_passes(self, frame_bgr: np.ndarray[Any, Any]) -> bool:
        """Return True if enough pixel motion warrants a YOLO run.

        frame_diff mode: compare grayscale delta against the previous frame.
        mog2 mode: use OpenCV MOG2 background subtractor (more stable across
        lighting changes; maintains a per-camera foreground model).

        Always returns True when motion_gate_enabled=False.
        First call always returns True (no baseline to compare against).

        Side effect: when the scene has been static for >= tracker_buffer_frames
        consecutive motion-gated frames, _last_tracklets is cleared so stale ghost
        tracks do not coast indefinitely on an empty scene.
        """
        settings = get_settings()
        if not settings.motion_gate_enabled:
            self._last_motion_mask = None
            return True

        if settings.motion_gate_method == "mog2":
            if self._mog2 is None:
                self._mog2 = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
            fg_mask: np.ndarray[Any, Any] = self._mog2.apply(frame_bgr)
            self._last_motion_mask = fg_mask
            changed_pct = float(np.count_nonzero(fg_mask)) / fg_mask.size * 100.0
        else:  # "frame_diff" (default)
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            if self._prev_frame_gray is None:
                self._prev_frame_gray = gray
                self._last_motion_mask = None
                return True  # first frame: no baseline yet, always run
            diff = cv2.absdiff(gray, self._prev_frame_gray)
            self._prev_frame_gray = gray
            pixel_mask = diff > _FRAME_DIFF_PIXEL_THRESHOLD
            self._last_motion_mask = (pixel_mask.astype(np.uint8)) * 255
            changed_pct = float(np.count_nonzero(pixel_mask)) / diff.size * 100.0

        passes = changed_pct >= settings.motion_gate_min_pixel_diff_pct

        if not passes:
            self._static_count += 1
            if self._static_count >= settings.tracker_buffer_frames:
                # Scene has been static too long — clear ghost tracks.
                self._last_tracklets = []
                self._prev_track_ids = set()
        else:
            self._static_count = 0

        return passes

    # ------------------------------------------------------------------
    # Adaptive interval (§6.0.3)
    # ------------------------------------------------------------------

    def _get_current_interval(self) -> int:
        """Return the effective YOLO interval for this frame."""
        settings = get_settings()
        if settings.detector_interval_adaptive:
            return self._adapt_interval
        return settings.detector_interval_frames

    def _update_adaptive_interval(self, tracklets: list[Tracklet]) -> None:
        """Adjust per-camera interval after a real YOLO run.

        A new person entering the FOV resets the interval to 1 immediately.
        N consecutive YOLO frames with no new entry raise it by one step (up to max).
        Only called when YOLO actually ran (not on motion-gated or interval-skipped frames).
        """
        settings = get_settings()
        if not settings.detector_interval_adaptive:
            return

        current_ids = {t.local_track_id for t in tracklets}
        new_ids = current_ids - self._prev_track_ids
        self._prev_track_ids = current_ids

        if new_ids:
            self._adapt_interval = 1
            self._no_new_detect_count = 0
        else:
            self._no_new_detect_count += 1
            if self._no_new_detect_count >= settings.detector_adapt_window:
                self._adapt_interval = min(
                    self._adapt_interval + 1,
                    settings.detector_interval_max,
                )
                self._no_new_detect_count = 0

    # ------------------------------------------------------------------
    # Main update
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_roi_bbox(
        mask: np.ndarray[Any, Any],
        h: int,
        w: int,
        margin_px: int,
    ) -> tuple[int, int, int, int] | None:
        """Return (x1, y1, x2, y2) from motion mask, expanded by margin_px, clamped to frame.

        Returns None when mask has no nonzero pixels or the resulting box is degenerate.
        """
        nz = cv2.findNonZero(mask)
        if nz is None:
            return None
        rx, ry, rw, rh = cv2.boundingRect(nz)
        x1 = max(0, rx - margin_px)
        y1 = max(0, ry - margin_px)
        x2 = min(w, rx + rw + margin_px)
        y2 = min(h, ry + rh + margin_px)
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2, y2

    def update(self, frame_bgr: np.ndarray[Any, Any], conf: float | None = None) -> list[Tracklet]:
        """Run pose detection + BoT-SORT tracking on one frame. Returns confirmed tracklets.

        Throttling order (each layer is independent; both must pass to run YOLO):
          1. Motion gate: skips YOLO if the scene is static (frame diff / MOG2).
          2. Interval gate: skips YOLO on non-scheduled frames; counter increments
             on every frame so the interval is wall-clock-stable regardless of gate.
          3. Cascade stages (SCRFD, AdaFace) in InferenceEngine are exempt — they
             keep their keypoint-based gate and are never interval-throttled.
        """
        # Increment counter on every frame so interval is stable even when the
        # motion gate blocks frames — per spec §6.0.25 "independent and additive".
        interval = self._get_current_interval()
        should_run = interval <= 1 or (self._frame_counter % interval) == 0
        self._frame_counter += 1

        if not self._motion_gate_passes(frame_bgr):
            return self._last_tracklets

        if not should_run:
            return self._last_tracklets

        settings = get_settings()

        # ROI crop: when enabled, crop YOLO input to the bounding box of changed
        # pixels (from the motion gate mask) and resize to a fixed 640x640.
        # Fixed size is mandatory — variable resolutions would generate a new TRT
        # engine plan per unique (H, W) pair, destroying the TRT cache benefit.
        frame_to_run = frame_bgr
        roi_offset_x = roi_offset_y = 0
        roi_scale_x = roi_scale_y = 1.0
        roi_crop_active = False
        if settings.motion_gate_roi_crop_enabled and self._last_motion_mask is not None:
            h_f, w_f = frame_bgr.shape[:2]
            roi = self._compute_roi_bbox(
                self._last_motion_mask, h_f, w_f, settings.motion_gate_roi_margin_px
            )
            if roi is not None:
                rx1, ry1, rx2, ry2 = roi
                crop = frame_bgr[ry1:ry2, rx1:rx2]
                frame_to_run = cv2.resize(crop, (640, 640), interpolation=cv2.INTER_LINEAR)
                roi_scale_x = (rx2 - rx1) / 640.0
                roi_scale_y = (ry2 - ry1) / 640.0
                roi_offset_x = rx1
                roi_offset_y = ry1
                roi_crop_active = True

        results = self._model.track(
            frame_to_run,
            conf=conf if conf is not None else settings.yolo_person_conf,
            persist=True,
            tracker=resolve_tracker_config(),
            verbose=False,
        )
        if not results:
            self._last_tracklets = []
            self._update_adaptive_interval([])
            return []
        r = results[0]
        boxes = r.boxes
        if boxes.id is None:
            self._last_tracklets = []
            self._update_adaptive_interval([])
            return []

        has_kpts = getattr(r, "keypoints", None) is not None
        kpts_data = r.keypoints.data if has_kpts else None  # (N, 17, 3) tensor

        tracklets: list[Tracklet] = []
        for i, (bbox_arr, tid, det_conf) in enumerate(
            zip(boxes.xyxy, boxes.id, boxes.conf, strict=False)
        ):
            x1, y1, x2, y2 = (int(v) for v in bbox_arr)

            if roi_crop_active:
                x1 = int(x1 * roi_scale_x) + roi_offset_x
                y1 = int(y1 * roi_scale_y) + roi_offset_y
                x2 = int(x2 * roi_scale_x) + roi_offset_x
                y2 = int(y2 * roi_scale_y) + roi_offset_y

            kpts: tuple[tuple[float, float, float], ...] = ()
            fv = False
            if kpts_data is not None and i < len(kpts_data):
                raw = kpts_data[i]  # (17, 3)
                if roi_crop_active:
                    kpts = tuple(
                        (
                            float(raw[j, 0]) * roi_scale_x + roi_offset_x,
                            float(raw[j, 1]) * roi_scale_y + roi_offset_y,
                            float(raw[j, 2]),
                        )
                        for j in range(min(KP_DIM, raw.shape[0]))
                    )
                else:
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
                    confidence=float(det_conf),
                    keypoints=kpts,
                    face_visible=fv,
                )
            )

        self._update_adaptive_interval(tracklets)
        self._last_tracklets = tracklets
        return tracklets
