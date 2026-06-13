"""CameraProfiler -- RTSP probe that measures stream quality and assigns tier."""

from __future__ import annotations

import logging
import struct
import time

import cv2
import numpy as np

from vms.api.schemas import ProfileData
from vms.config import get_settings
from vms.profiler.tier import assign_tier

logger = logging.getLogger(__name__)


class CameraProfiler:
    """Probes an RTSP stream and returns a populated ProfileData."""

    def __init__(
        self,
        probe_duration_s: int | None = None,
        sample_frames: int | None = None,
    ) -> None:
        s = get_settings()
        self._duration = (
            probe_duration_s if probe_duration_s is not None else s.profiler_probe_duration_s
        )
        self._sample_n = sample_frames if sample_frames is not None else s.profiler_sample_frames

    def probe(self, rtsp_url: str) -> ProfileData:
        """Open *rtsp_url*, measure for up to _duration seconds, return ProfileData."""
        cap = cv2.VideoCapture(rtsp_url)
        try:
            return self._run(cap, rtsp_url)
        finally:
            cap.release()

    def _run(self, cap: cv2.VideoCapture, url: str) -> ProfileData:
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open RTSP stream: {url}")

        s = get_settings()
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, s.profiler_rtsp_open_timeout_ms)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, s.profiler_rtsp_read_timeout_ms)

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        declared_fps = cap.get(cv2.CAP_PROP_FPS)
        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = self._decode_fourcc(fourcc_int)

        frames: list[np.ndarray] = []  # type: ignore[type-arg]
        decoded = 0
        failed = 0
        deadline = time.monotonic() + self._duration if self._duration > 0 else None

        while True:
            if deadline is not None and time.monotonic() >= deadline:
                break
            ok, frame = cap.read()
            if not ok:
                failed += 1
                if failed > 30:
                    break
                continue
            decoded += 1
            if len(frames) < self._sample_n:
                frames.append(frame.copy())
            if deadline is None and decoded >= self._sample_n:
                break

        if self._duration == 0 and decoded < int(0.8 * self._sample_n):
            raise RuntimeError(
                f"Insufficient frames: got {decoded}, need {int(0.8 * self._sample_n)}"
            )

        total = decoded + failed
        drop_rate = (failed / total) if total > 0 else 0.0
        fps_measured = float(decoded / self._duration) if self._duration > 0 else declared_fps

        focus_score: float | None = None
        brightness_mean: float | None = None
        is_analog: bool | None = None

        if frames:
            focus_scores = [
                float(cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
                for f in frames
            ]
            focus_score = float(np.mean(focus_scores))

            brightness_vals = [float(np.mean(f)) for f in frames]
            brightness_mean = float(np.mean(brightness_vals))

            is_analog = self._detect_deinterlace_combing(frames)

        shutter_suggestion, shutter_confidence = self._detect_shutter_type(frames)

        data = ProfileData(
            resolution_w=width,
            resolution_h=height,
            fps_measured=fps_measured,
            focus_score=focus_score,
            frame_drop_rate=drop_rate,
            brightness_mean=brightness_mean,
            is_analog_via_encoder=is_analog,
            codec=codec,
            shutter_suggestion=shutter_suggestion,
            shutter_confidence=shutter_confidence,
        )

        tier, tier_reason = assign_tier(data)
        data = data.model_copy(update={"suggested_tier": tier, "tier_reason": tier_reason})
        return data

    @staticmethod
    def _decode_fourcc(fourcc: int) -> str:
        try:
            return struct.pack("<I", fourcc).decode("ascii", errors="replace").strip("\x00")
        except Exception:
            return "UNKN"

    @staticmethod
    def _detect_deinterlace_combing(frames: list[np.ndarray]) -> bool:  # type: ignore[type-arg]
        """Return True if alternating-row intensity variance suggests deinterlace combing."""
        if not frames:
            return False
        scores: list[float] = []
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
            even_mean = float(gray[::2].mean())
            odd_mean = float(gray[1::2].mean())
            scores.append(abs(even_mean - odd_mean))
        mean_diff = float(np.mean(scores))
        return mean_diff > 20.0

    @staticmethod
    def _detect_shutter_type(
        frames: list[np.ndarray],  # type: ignore[type-arg]
    ) -> tuple[str, float]:
        """Estimate shutter type from optical-flow skew variance across frames.

        Returns (suggestion, confidence) where suggestion in {'rolling','global','unknown'}.
        Skew variance > threshold -> rolling (confidence clamped 60-95%).
        """
        if len(frames) < 4:
            return "unknown", 0.5

        s = get_settings()
        threshold = s.profiler_shutter_skew_threshold

        gray_frames = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
        skew_variances: list[float] = []

        h, w = gray_frames[0].shape[:2]
        flow_buf: np.ndarray = np.zeros((h, w, 2), dtype=np.float32)  # type: ignore[type-arg]
        for i in range(len(gray_frames) - 1):
            flow = cv2.calcOpticalFlowFarneback(
                gray_frames[i],
                gray_frames[i + 1],
                flow_buf,
                0.5,
                3,
                15,
                3,
                5,
                1.2,
                0,
            )
            h_flow = flow[..., 0]
            row_means = h_flow.mean(axis=1)
            skew_variances.append(float(np.var(row_means)))

        mean_skew = float(np.mean(skew_variances))

        if mean_skew > threshold:
            confidence = min(0.95, max(0.60, 1.0 - mean_skew / (threshold * 2.5)))
            return "rolling", round(confidence, 2)
        elif mean_skew < threshold * 0.5:
            confidence = min(0.95, max(0.60, 1.0 - mean_skew / threshold))
            return "global", round(confidence, 2)
        return "unknown", 0.5
