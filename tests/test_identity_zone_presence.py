from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.orm import Session

from vms.db.models import Zone, ZonePresence
from vms.identity.zone_presence import ZonePresenceTracker, point_in_polygon

# ── pure geometry ─────────────────────────────────────────────────────


def test_point_in_polygon_inside() -> None:
    poly = [[0, 0], [100, 0], [100, 100], [0, 100]]
    assert point_in_polygon(50.0, 50.0, poly) is True


def test_point_in_polygon_outside() -> None:
    poly = [[0, 0], [100, 0], [100, 100], [0, 100]]
    assert point_in_polygon(200.0, 200.0, poly) is False


def test_point_in_polygon_does_not_crash_on_boundary() -> None:
    poly = [[0, 0], [100, 0], [100, 100], [0, 100]]
    point_in_polygon(0.0, 0.0, poly)  # boundary -- no assertion, just must not raise


# ── integration tests ─────────────────────────────────────────────────


@pytest.fixture()
def zone(db_session: Session) -> Zone:
    poly = [[0, 0], [500, 0], [500, 500], [0, 500]]
    z = Zone(name="Test Zone", polygon_json=json.dumps(poly))
    db_session.add(z)
    db_session.flush()
    return z


@pytest.mark.integration
def test_tracker_opens_presence_on_zone_entry(db_session: Session, zone: Zone) -> None:
    tracker = ZonePresenceTracker(db=db_session)
    gid = uuid.uuid4()
    tracker.update(global_track_id=gid, floor_x=100.0, floor_y=100.0)
    db_session.flush()

    rows = db_session.query(ZonePresence).filter_by(global_track_id=gid, zone_id=zone.zone_id).all()
    assert len(rows) == 1
    assert rows[0].exited_at is None


@pytest.mark.integration
def test_tracker_closes_presence_on_zone_exit(db_session: Session, zone: Zone) -> None:
    tracker = ZonePresenceTracker(db=db_session)
    gid = uuid.uuid4()
    tracker.update(global_track_id=gid, floor_x=100.0, floor_y=100.0)  # enters
    db_session.flush()
    tracker.update(global_track_id=gid, floor_x=9999.0, floor_y=9999.0)  # exits
    db_session.flush()

    rows = db_session.query(ZonePresence).filter_by(global_track_id=gid, zone_id=zone.zone_id).all()
    assert len(rows) == 1
    assert rows[0].exited_at is not None


@pytest.mark.integration
def test_tracker_ignores_tracklet_with_no_zone_match(db_session: Session, zone: Zone) -> None:
    tracker = ZonePresenceTracker(db=db_session)
    gid = uuid.uuid4()
    tracker.update(global_track_id=gid, floor_x=9999.0, floor_y=9999.0)
    db_session.flush()

    rows = db_session.query(ZonePresence).filter_by(global_track_id=gid).all()
    assert rows == []
