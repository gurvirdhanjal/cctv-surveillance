from __future__ import annotations

from vms.ingestion.messages import FramePointer


def test_frame_pointer_round_trips_through_redis_fields() -> None:
    fp = FramePointer(
        cam_id=3, shm_name="vms_cam_3", seq_id=99, timestamp_ms=12345, width=1920, height=1080
    )
    fields = fp.to_redis_fields()
    recovered = FramePointer.from_redis_fields(fields)
    assert recovered == fp


def test_frame_pointer_is_immutable() -> None:
    fp = FramePointer(cam_id=1, shm_name="x", seq_id=0, timestamp_ms=0, width=640, height=480)
    try:
        fp.cam_id = 99  # type: ignore[misc]
        raise AssertionError("Should have raised FrozenInstanceError")
    except Exception:
        pass
