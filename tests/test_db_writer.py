"""Tests for vms.writer.db_writer — flush_detection_frame idempotent batch insert."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from vms.db.models import Camera, TrackingEvent
from vms.identity.engine import IdentityEngine
from vms.identity.faiss_index import FaissIndex
from vms.identity.reid import ReIdService
from vms.identity.zone_presence import ZonePresenceTracker
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


def _make_identity_frame(
    camera_id: int = 1, track_id: int = 7, ts_offset: int = 0
) -> DetectionFrame:
    return DetectionFrame(
        camera_id=camera_id,
        seq_id=1 + ts_offset,
        timestamp_ms=1_700_000_000_000 + ts_offset * 1000,
        tracklets=(
            Tracklet(
                local_track_id=track_id,
                camera_id=camera_id,
                bbox=(10, 20, 110, 220),
                confidence=0.9,
                embedding=tuple([0.1] * 512),
            ),
        ),
        face_embeddings=(),
    )


@pytest.mark.integration
def test_flush_uses_identity_engine_for_global_track_id(db_session: Session) -> None:
    cam = Camera(name="Cam1", rtsp_url="rtsp://x/1", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()

    engine = IdentityEngine(ReIdService(FaissIndex()))
    zone_tracker = ZonePresenceTracker()
    frame = _make_identity_frame(camera_id=cam.camera_id, track_id=5)

    flush_detection_frame(
        db_session,
        frame,
        identity=engine,
        homography_json=None,
        zone_tracker=zone_tracker,
    )
    db_session.flush()

    row = db_session.query(TrackingEvent).filter_by(
        camera_id=cam.camera_id, local_track_id="5"
    ).first()
    assert row is not None
    gid1 = str(row.global_track_id)

    # Second flush of same tracklet — must reuse same global_track_id
    flush_detection_frame(
        db_session,
        _make_identity_frame(camera_id=cam.camera_id, track_id=5, ts_offset=1),
        identity=engine,
        homography_json=None,
        zone_tracker=zone_tracker,
    )
    db_session.flush()

    rows = db_session.query(TrackingEvent).filter_by(
        camera_id=cam.camera_id, local_track_id="5"
    ).all()
    assert len(rows) == 2
    assert all(str(r.global_track_id) == gid1 for r in rows)


@pytest.mark.integration
def test_flush_without_identity_still_works(db_session: Session) -> None:
    cam = Camera(name="Cam2", rtsp_url="rtsp://x/2", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()

    flush_detection_frame(db_session, _make_identity_frame(camera_id=cam.camera_id))
    db_session.flush()

    row = db_session.query(TrackingEvent).filter_by(camera_id=cam.camera_id).first()
    assert row is not None
    assert row.global_track_id is not None
