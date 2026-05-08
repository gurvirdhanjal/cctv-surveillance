"""Tests for tracking ORM models: TrackingEvent, ReidMatch, ZonePresence."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vms.db.models import Camera, ReidMatch, TrackingEvent, Zone, ZonePresence

_TS = datetime(2026, 5, 1, 8, 0, 0)


def _camera(db_session: Session) -> Camera:
    cam = Camera(name="Cam-Track", rtsp_url="rtsp://t/s")
    db_session.add(cam)
    db_session.commit()
    return cam


def test_tracking_event_insert(db_session: Session) -> None:
    cam = _camera(db_session)
    gid = uuid.uuid4()
    ev = TrackingEvent(
        camera_id=cam.camera_id,
        local_track_id="t1",
        global_track_id=gid,
        event_ts=_TS,
        ingest_ts=_TS,
        bbox_x1=10,
        bbox_y1=20,
        bbox_x2=100,
        bbox_y2=200,
        seq_id=1,
    )
    db_session.add(ev)
    db_session.commit()
    assert ev.event_id is not None


def test_tracking_event_bbox_invalid(db_session: Session) -> None:
    cam = _camera(db_session)
    ev = TrackingEvent(
        camera_id=cam.camera_id,
        local_track_id="t2",
        global_track_id=uuid.uuid4(),
        event_ts=_TS,
        ingest_ts=_TS,
        bbox_x1=100,
        bbox_y1=20,
        bbox_x2=10,  # x2 < x1 — should fail
        bbox_y2=200,
        seq_id=2,
    )
    db_session.add(ev)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_tracking_event_idempotency_unique(db_session: Session) -> None:
    cam = _camera(db_session)
    gid = uuid.uuid4()
    args = dict(
        camera_id=cam.camera_id,
        local_track_id="t3",
        global_track_id=gid,
        event_ts=_TS,
        ingest_ts=_TS,
        bbox_x1=0,
        bbox_y1=0,
        bbox_x2=10,
        bbox_y2=10,
        seq_id=3,
    )
    db_session.add(TrackingEvent(**args))
    db_session.commit()
    db_session.add(TrackingEvent(**args))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_reid_match_insert(db_session: Session) -> None:
    match = ReidMatch(
        global_track_id_1=uuid.uuid4(),
        global_track_id_2=uuid.uuid4(),
        similarity=0.91,
        event_ts=_TS,
    )
    db_session.add(match)
    db_session.commit()
    assert match.reid_match_id is not None


def test_zone_presence_insert(db_session: Session) -> None:
    zone = Zone(name="Zone-A")
    db_session.add(zone)
    db_session.commit()
    zp = ZonePresence(
        zone_id=zone.zone_id,
        global_track_id=uuid.uuid4(),
        entered_at=_TS,
    )
    db_session.add(zp)
    db_session.commit()
    assert zp.presence_id is not None
    assert zp.exited_at is None


def test_zone_presence_temporal_constraint(db_session: Session) -> None:
    zone = Zone(name="Zone-B")
    db_session.add(zone)
    db_session.commit()
    zp = ZonePresence(
        zone_id=zone.zone_id,
        global_track_id=uuid.uuid4(),
        entered_at=datetime(2026, 5, 1, 10, 0, 0),
        exited_at=datetime(2026, 5, 1, 9, 0, 0),  # before entered — invalid
    )
    db_session.add(zp)
    with pytest.raises(IntegrityError):
        db_session.commit()
