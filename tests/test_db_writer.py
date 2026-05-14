"""Tests for vms.writer.db_writer — flush_detection_frame idempotent batch insert."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from vms.db.models import Camera, TrackingEvent
from vms.inference.messages import DetectionFrame, Tracklet
from vms.writer.db_writer import flush_detection_frame


@pytest.fixture()
def camera(db_session: Session) -> Camera:
    """Insert a Camera row to satisfy the FK on tracking_events.camera_id."""
    cam = Camera(
        name="test-cam",
        rtsp_url="rtsp://localhost/test",
        capability_tier="FULL",
        worker_group=1,
    )
    db_session.add(cam)
    db_session.flush()
    return cam


def _make_frame(camera_id: int, seq_id: int = 0) -> DetectionFrame:
    return DetectionFrame(
        camera_id=camera_id,
        seq_id=seq_id,
        timestamp_ms=1_000_000,
        tracklets=(
            Tracklet(
                local_track_id=10,
                camera_id=camera_id,
                bbox=(0, 0, 100, 200),
                confidence=0.9,
            ),
        ),
        face_embeddings=(),
    )


@pytest.mark.integration
def test_flush_detection_frame_inserts_tracking_event(db_session: Session, camera: Camera) -> None:
    frame = _make_frame(camera_id=camera.camera_id)
    flush_detection_frame(db_session, frame)
    db_session.flush()

    rows = (
        db_session.query(TrackingEvent)
        .filter_by(camera_id=camera.camera_id, local_track_id="10")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].bbox_x1 == 0
    assert rows[0].bbox_x2 == 100
    assert rows[0].global_track_id is not None


@pytest.mark.integration
def test_flush_detection_frame_is_idempotent(db_session: Session, camera: Camera) -> None:
    frame = _make_frame(camera_id=camera.camera_id, seq_id=1)
    flush_detection_frame(db_session, frame)
    flush_detection_frame(db_session, frame)  # second call must not raise
    db_session.flush()

    rows = (
        db_session.query(TrackingEvent)
        .filter_by(camera_id=camera.camera_id, local_track_id="10")
        .all()
    )
    assert len(rows) == 1  # deduplicated by uq_tracking_idem


@pytest.mark.integration
def test_flush_detection_frame_no_op_for_empty_tracklets(
    db_session: Session, camera: Camera
) -> None:
    frame = DetectionFrame(
        camera_id=camera.camera_id,
        seq_id=0,
        timestamp_ms=0,
        tracklets=(),
        face_embeddings=(),
    )
    flush_detection_frame(db_session, frame)  # must not raise
    db_session.flush()
    rows = db_session.query(TrackingEvent).filter_by(camera_id=camera.camera_id).all()
    assert rows == []
