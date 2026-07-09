"""Decode backends: camera stream URL → BGR frames (Phase 6d).

DecodeBackend mirrors the InferenceBackend pattern from Phase 6c: structural
typing so tests can drive the worker with plain fakes. OpenCvDecoder is the
extracted current behaviour (CPU FFmpeg via cv2.VideoCapture); NvdecDecoder
(GPU video engine) lands in Task 3.
"""

from __future__ import annotations

import logging
import re
import subprocess
from functools import lru_cache
from typing import Protocol, runtime_checkable

import cv2
import numpy as np

from vms.config import get_settings
from vms.inference.gpu_profile import detect_gpu_profile

logger = logging.getLogger(__name__)

_CREDENTIALS_RE = re.compile(r"//[^/@]+@")


def _mask_url(url: str) -> str:
    """Strip credentials from stream URLs before logging (CLAUDE.md §7.2)."""
    return _CREDENTIALS_RE.sub("//***@", url)


@lru_cache(maxsize=1)
def nvdec_available() -> bool:
    """True when a CUDA GPU with an NVDEC unit AND a cuvid-enabled FFmpeg exist."""
    profile = detect_gpu_profile()
    if profile is None or profile.nvdec_units < 1:
        logger.info("NVDEC unavailable: no CUDA GPU with a video decode unit")
        return False
    settings = get_settings()
    try:
        result = subprocess.run(
            [settings.nvdec_ffmpeg_path, "-hide_banner", "-decoders"],
            capture_output=True,
            text=True,
            timeout=settings.nvdec_probe_timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning(
            "NVDEC unavailable: ffmpeg binary not runnable at '%s'", settings.nvdec_ffmpeg_path
        )
        return False
    if "h264_cuvid" not in result.stdout:
        logger.warning(
            "NVDEC unavailable: ffmpeg at '%s' lacks cuvid decoders", settings.nvdec_ffmpeg_path
        )
        return False
    return True


def probe_codec(url: str) -> str | None:
    """Video codec of the stream: 'h264', 'hevc', or None (probe failed/unsupported)."""
    settings = get_settings()
    cmd = [
        settings.nvdec_ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=nw=1:nk=1",
    ]
    if url.startswith("rtsp://"):
        cmd += ["-rtsp_transport", "tcp"]
    cmd.append(url)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=settings.nvdec_probe_timeout_s
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("codec probe failed to run for %s", _mask_url(url))
        return None
    if result.returncode != 0:
        logger.warning("codec probe returned %d for %s", result.returncode, _mask_url(url))
        return None
    codec = result.stdout.strip().splitlines()[0].strip() if result.stdout.strip() else ""
    if codec not in ("h264", "hevc"):
        logger.warning("codec '%s' not NVDEC-decodable for %s", codec, _mask_url(url))
        return None
    return codec


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
