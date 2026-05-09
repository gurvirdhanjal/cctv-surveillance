"""Shared memory slot for single-camera frame exchange between processes.

Layout: first 16 bytes = header (seq_id: uint64 LE, timestamp_ms: uint64 LE),
followed by raw BGR frame bytes (height * width * 3).
"""

from __future__ import annotations

import struct
import time
from multiprocessing.shared_memory import SharedMemory

import numpy as np

from vms.config import get_settings

_HEADER_SIZE = 16
_HEADER_FMT = "<QQ"  # little-endian: seq_id (uint64) + timestamp_ms (uint64)


class SHMSlot:
    """One shared memory region for one camera frame."""

    def __init__(self, name: str, width: int, height: int, shm: SharedMemory) -> None:
        self.name = name
        self.width = width
        self.height = height
        self._frame_bytes = width * height * 3
        self._shm = shm

    @classmethod
    def create(cls, name: str, width: int, height: int) -> SHMSlot:
        """Allocate a new SHM segment. Caller owns cleanup via close() + unlink()."""
        total = _HEADER_SIZE + width * height * 3
        shm = SharedMemory(name=name, create=True, size=total)
        return cls(name, width, height, shm)

    def write(self, frame: np.ndarray[tuple[int, int, int], np.dtype[np.uint8]], seq_id: int) -> int:
        """Write BGR frame and header. Returns the timestamp_ms recorded."""
        ts_ms = int(time.monotonic() * 1000)
        self._shm.buf[:_HEADER_SIZE] = struct.pack(_HEADER_FMT, seq_id, ts_ms)
        raw = frame.tobytes()
        self._shm.buf[_HEADER_SIZE : _HEADER_SIZE + len(raw)] = raw
        return ts_ms

    def read(self) -> tuple[np.ndarray[tuple[int, int, int], np.dtype[np.uint8]], int, int] | None:
        """Read frame. Returns (frame_bgr, seq_id, timestamp_ms) or None if stale."""
        seq_id, timestamp_ms = struct.unpack(_HEADER_FMT, bytes(self._shm.buf[:_HEADER_SIZE]))
        now_ms = int(time.monotonic() * 1000)
        if now_ms - timestamp_ms > get_settings().stale_threshold_ms:
            return None
        raw = bytes(self._shm.buf[_HEADER_SIZE : _HEADER_SIZE + self._frame_bytes])
        frame = np.frombuffer(raw, dtype=np.uint8).reshape(self.height, self.width, 3).copy()
        return frame, seq_id, timestamp_ms

    def close(self) -> None:
        self._shm.close()

    def unlink(self) -> None:
        self._shm.unlink()
