"""Decode backends: camera stream URL → BGR frames (Phase 6d).

DecodeBackend mirrors the InferenceBackend pattern from Phase 6c: structural
typing so tests can drive the worker with plain fakes. OpenCvDecoder is the
extracted current behaviour (CPU FFmpeg via cv2.VideoCapture); NvdecDecoder
(GPU video engine) lands in Task 3.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@runtime_checkable
class DecodeBackend(Protocol):
    def read(self) -> tuple[bool, np.ndarray | None]:
        """Blocking read of the next frame. (False, None) on failure/EOF."""
        ...

    def get_resolution(self) -> tuple[int, int]:
        """(width, height) as reported by the stream; (0, 0) when unknown."""
        ...

    def release(self) -> None:
        """Release all resources. Idempotent."""
        ...


class OpenCvDecoder:
    """CPU decode via cv2.VideoCapture — the pre-Phase-6d behaviour, unchanged."""

    def __init__(self, url: str) -> None:
        self._cap = cv2.VideoCapture(url)
        # Limit OpenCV's internal RTSP buffer to 1 frame so stale frames are dropped
        # automatically when the consumer falls behind, keeping display at real-time.
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self) -> tuple[bool, np.ndarray | None]:
        ret, frame = self._cap.read()
        return bool(ret), frame

    def get_resolution(self) -> tuple[int, int]:
        # Best-effort for RTSP; cameras that don't report before the first frame return 0.
        return (
            int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )

    def release(self) -> None:
        self._cap.release()
