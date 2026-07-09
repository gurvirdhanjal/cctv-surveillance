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
import threading
from collections.abc import Callable
from functools import lru_cache
from typing import IO, Any, Protocol, runtime_checkable

import cv2
import numpy as np

from vms.config import get_settings
from vms.inference.gpu_profile import detect_gpu_profile

logger = logging.getLogger(__name__)

_CREDENTIALS_RE = re.compile(r"//[^/@]+@")
# Grace period when reaping the ffmpeg child on release/restart (shutdown hygiene,
# not a tuning knob — the worker's rtsp_failure_threshold governs giving up).
_TERMINATE_GRACE_S = 2.0


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


def build_nvdec_command(
    url: str, codec: str, width: int, height: int, *, ffmpeg_path: str
) -> list[str]:
    """FFmpeg argv for NVDEC decode to raw bgr24 frames on stdout.

    -c:v {codec}_cuvid and -resize are cuvid input options and MUST precede -i;
    -resize scales on the NVDEC engine, so the pipe carries analytics-resolution
    frames (width*height*3 bytes each), not source resolution.
    """
    cmd = [ffmpeg_path, "-nostdin", "-loglevel", "warning"]
    if url.startswith("rtsp://"):
        cmd += ["-rtsp_transport", "tcp"]
    cmd += [
        "-c:v",
        f"{codec}_cuvid",
        "-resize",
        f"{width}x{height}",
        "-i",
        url,
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "pipe:1",
    ]
    return cmd


class NvdecDecoder:
    """GPU decode via an FFmpeg h264_cuvid/hevc_cuvid subprocess (GPU spec §6.3).

    Frames arrive as exact width*height*3 bgr24 buffers on stdout. Short reads
    count as failures; after nvdec_restart_after_failures consecutive failures the
    subprocess is transparently killed and relaunched (the worker's backoff +
    rtsp_failure_threshold still govern giving up entirely).
    """

    def __init__(
        self,
        url: str,
        codec: str,
        width: int,
        height: int,
        *,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        on_release: Callable[[], None] | None = None,
    ) -> None:
        self._url = url
        self._codec = codec
        self._width = width
        self._height = height
        self._frame_bytes = width * height * 3
        self._popen_factory = popen_factory
        self._on_release = on_release
        self._proc: Any = None
        self._stderr_thread: threading.Thread | None = None
        self._consecutive_failures = 0
        self._released = False
        self._start()

    def _start(self) -> None:
        settings = get_settings()
        cmd = build_nvdec_command(
            self._url,
            self._codec,
            self._width,
            self._height,
            ffmpeg_path=settings.nvdec_ffmpeg_path,
        )
        self._proc = self._popen_factory(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            bufsize=self._frame_bytes * 2,
        )
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, args=(self._proc.stderr,), daemon=True
        )
        self._stderr_thread.start()

    def _drain_stderr(self, stderr: IO[bytes]) -> None:
        masked = _mask_url(self._url)
        try:
            for line in iter(stderr.readline, b""):
                logger.debug("ffmpeg[%s]: %s", masked, line.decode(errors="replace").rstrip())
        except Exception:  # drain thread must never crash the worker
            pass

    def _read_exact(self) -> bytes | None:
        stdout: IO[bytes] = self._proc.stdout
        buf = bytearray()
        while len(buf) < self._frame_bytes:
            chunk = stdout.read(self._frame_bytes - len(buf))
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._proc is None:
            return False, None
        data = self._read_exact()
        if data is None:
            self._consecutive_failures += 1
            if self._consecutive_failures >= get_settings().nvdec_restart_after_failures:
                logger.warning("NVDEC subprocess stalled for %s — restarting", _mask_url(self._url))
                self._reap()
                self._start()
                self._consecutive_failures = 0
            return False, None
        self._consecutive_failures = 0
        frame = np.frombuffer(data, dtype=np.uint8).reshape(self._height, self._width, 3)
        return True, frame

    def get_resolution(self) -> tuple[int, int]:
        return self._width, self._height

    def _reap(self) -> None:
        proc = self._proc
        if proc is None:
            return
        self._proc = None
        try:
            proc.terminate()
            try:
                proc.wait(timeout=_TERMINATE_GRACE_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=_TERMINATE_GRACE_S)
        except Exception:  # best-effort reap; never raise on shutdown
            logger.warning("failed to reap ffmpeg child for %s", _mask_url(self._url))

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._reap()
        if self._on_release is not None:
            self._on_release()


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
