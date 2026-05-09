from __future__ import annotations

import time
from unittest.mock import patch

import numpy as np
import pytest

from vms.ingestion.shm import (
    HEADER_FMT,
    HEADER_SIZE,
    SHMSlot,
)


def test_header_constants_are_exported() -> None:
    """Verify HEADER_FMT and HEADER_SIZE are exported for use by other modules."""
    assert HEADER_SIZE == 16
    assert HEADER_FMT == "<QQ"


@pytest.fixture
def slot() -> SHMSlot:
    s = SHMSlot.create("vms_test_slot_task2", width=64, height=48)
    yield s
    try:
        s.close()
        s.unlink()
    except Exception:
        pass


def test_shm_slot_write_then_read_returns_frame(slot: SHMSlot) -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    frame[10, 20] = [100, 150, 200]
    slot.write(frame, seq_id=1)
    result = slot.read()
    assert result is not None
    out_frame, seq_id, _ts = result
    assert out_frame.shape == (48, 64, 3)
    assert list(out_frame[10, 20]) == [100, 150, 200]
    assert seq_id == 1


def test_shm_slot_read_returns_none_when_stale(slot: SHMSlot) -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    slot.write(frame, seq_id=1)
    real_ns = time.time_ns()
    with patch("vms.ingestion.shm.time") as mock_time:
        # Simulate current time 1 second (1_000_000_000 ns) in the future
        mock_time.time_ns.return_value = real_ns + 1_000_000_000
        result = slot.read()
    assert result is None


def test_shm_slot_seq_id_is_preserved(slot: SHMSlot) -> None:
    frame = np.zeros((48, 64, 3), dtype=np.uint8)
    slot.write(frame, seq_id=42)
    result = slot.read()
    assert result is not None
    _, seq_id, _ = result
    assert seq_id == 42
