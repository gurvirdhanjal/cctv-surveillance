"""Tests for PersonClipEmbedding ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vms.db.models import Camera, PersonClipEmbedding

_TS = datetime(2026, 5, 1, 10, 0, 0)
_TS2 = datetime(2026, 5, 1, 10, 0, 1)
_DUMMY_EMB = [0.0] * 512


def _cam(db_session: Session) -> Camera:
    cam = Camera(name="forensic-cam", rtsp_url="rtsp://f/s")
    db_session.add(cam)
    db_session.commit()
    return cam


def test_clip_embedding_insert(db_session: Session) -> None:
    cam = _cam(db_session)
    gid = uuid.uuid4()
    emb = PersonClipEmbedding(
        global_track_id=gid,
        camera_id=cam.camera_id,
        event_ts=_TS,
        embedding=_DUMMY_EMB,
        snapshot_path="snapshots/2026/05/01/abc.jpg",
    )
    db_session.add(emb)
    db_session.commit()
    assert emb.clip_emb_id is not None


def test_clip_embedding_unique_track_ts(db_session: Session) -> None:
    cam = _cam(db_session)
    gid = uuid.uuid4()
    for _ in range(2):
        db_session.add(
            PersonClipEmbedding(
                global_track_id=gid,
                camera_id=cam.camera_id,
                event_ts=_TS,
                embedding=_DUMMY_EMB,
                snapshot_path="snapshots/dup.jpg",
            )
        )
    with pytest.raises(IntegrityError):
        db_session.commit()
