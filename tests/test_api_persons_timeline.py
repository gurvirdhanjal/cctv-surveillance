"""Tests for GET /api/persons/{person_id}/timeline (Phase 4P Task 1b, spec §9.2)."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.db.audit import compute_row_hash
from vms.db.models import (
    AuditLog,
    Camera,
    Person,
    TrackingEvent,
    User,
    UserCameraPermission,
    Zone,
)


def _auth(role: str = "manager", user_id: int = 1) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, role)}"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_person(db: Session, purged: bool = False) -> Person:
    person = Person(name="Brijesh Kumar", employee_id=f"E{uuid.uuid4().hex[:8]}")
    if purged:
        person.is_active = False
        person.purged_at = _utcnow()
    db.add(person)
    db.flush()
    return person


def _seed_camera(db: Session, name: str | None = None) -> int:
    cam = Camera(
        name=name or f"TL_{uuid.uuid4().hex[:6]}", rtsp_url="rtsp://x", capability_tier="FULL"
    )
    db.add(cam)
    db.flush()
    return cam.camera_id


def _seed_zone(db: Session, name: str = "Assembly") -> int:
    zone = Zone(name=f"{name}_{uuid.uuid4().hex[:4]}")
    db.add(zone)
    db.flush()
    return zone.zone_id


def _seed_event(
    db: Session,
    person_id: int | None,
    camera_id: int,
    ts: datetime,
    gid: uuid.UUID | None = None,
    zone_id: int | None = None,
    resolved_via: str | None = None,
    floor_x: float | None = None,
    floor_y: float | None = None,
    track: str = "t1",
) -> uuid.UUID:
    gid = gid or uuid.uuid4()
    db.add(
        TrackingEvent(
            camera_id=camera_id,
            local_track_id=track,
            global_track_id=gid,
            person_id=person_id,
            zone_id=zone_id,
            event_ts=ts,
            ingest_ts=ts,
            bbox_x1=10,
            bbox_y1=10,
            bbox_x2=50,
            bbox_y2=90,
            floor_x=floor_x,
            floor_y=floor_y,
            resolved_via=resolved_via,
            seq_id=1,
        )
    )
    db.flush()
    return gid


async def _get(path: str, db: Session, role: str = "manager", user_id: int = 1) -> tuple[int, Any]:
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(path, headers=_auth(role, user_id))
    finally:
        app.dependency_overrides.clear()
    return resp.status_code, (resp.json() if resp.content else {})


# -- coalescing ---------------------------------------------------------------


async def test_timeline_coalesces_events_into_visit_spans(db_session: Session) -> None:
    person = _seed_person(db_session)
    cam_a = _seed_camera(db_session)
    cam_b = _seed_camera(db_session)
    t0 = _utcnow().replace(microsecond=0) - timedelta(hours=1)
    gid_a = uuid.uuid4()

    # cam A, one track: t0, +5s, +8s (gaps < 10s -> one span); +30s (gap 22s -> new span)
    _seed_event(db_session, person.person_id, cam_a, t0, gid=gid_a)
    _seed_event(db_session, person.person_id, cam_a, t0 + timedelta(seconds=5), gid=gid_a)
    _seed_event(db_session, person.person_id, cam_a, t0 + timedelta(seconds=8), gid=gid_a)
    _seed_event(db_session, person.person_id, cam_a, t0 + timedelta(seconds=30), gid=gid_a)
    # cam B: camera change always splits, even with a tiny gap
    _seed_event(db_session, person.person_id, cam_b, t0 + timedelta(seconds=3))

    status, body = await _get(f"/api/persons/{person.person_id}/timeline", db_session)

    assert status == 200
    spans = body["spans"]
    assert len(spans) == 3
    assert body["truncated"] is False
    # ordered by from_ts DESC
    assert spans[0]["camera_id"] == cam_a
    assert spans[0]["from_ts"] == (t0 + timedelta(seconds=30)).isoformat()
    assert spans[0]["to_ts"] == (t0 + timedelta(seconds=30)).isoformat()
    assert spans[1]["camera_id"] == cam_b
    assert spans[2]["camera_id"] == cam_a
    assert spans[2]["from_ts"] == t0.isoformat()
    assert spans[2]["to_ts"] == (t0 + timedelta(seconds=8)).isoformat()
    assert spans[2]["camera_name"]  # joined from cameras


async def test_timeline_new_track_id_splits_span_on_same_camera(db_session: Session) -> None:
    person = _seed_person(db_session)
    cam = _seed_camera(db_session)
    t0 = _utcnow().replace(microsecond=0) - timedelta(minutes=30)

    _seed_event(db_session, person.person_id, cam, t0)
    _seed_event(db_session, person.person_id, cam, t0 + timedelta(seconds=2))  # new gid

    status, body = await _get(f"/api/persons/{person.person_id}/timeline", db_session)

    assert status == 200
    assert len(body["spans"]) == 2


# -- span payload -------------------------------------------------------------


async def test_timeline_span_payload_fields(db_session: Session) -> None:
    person = _seed_person(db_session)
    cam = _seed_camera(db_session, name="Gate 105")
    zone = _seed_zone(db_session)
    t0 = _utcnow().replace(microsecond=0) - timedelta(minutes=10)
    gid = uuid.uuid4()

    # mixed resolved_via: face must win; floor coords: latest NON-NULL wins
    _seed_event(
        db_session,
        person.person_id,
        cam,
        t0,
        gid=gid,
        zone_id=zone,
        resolved_via="body",
        floor_x=5.0,
        floor_y=7.5,
    )
    _seed_event(
        db_session,
        person.person_id,
        cam,
        t0 + timedelta(seconds=4),
        gid=gid,
        zone_id=zone,
        resolved_via="face",
    )

    status, body = await _get(f"/api/persons/{person.person_id}/timeline", db_session)

    assert status == 200
    span = body["spans"][0]
    assert span["camera_name"] == "Gate 105"
    assert span["zone_id"] == zone
    assert span["zone_name"] is not None
    assert span["global_track_id"] == str(gid)
    assert span["resolved_via"] == "face"
    assert span["floor_x"] == 5.0
    assert span["floor_y"] == 7.5
    assert span["thumbnail_url"] is None


# -- window + filters + limits ------------------------------------------------


async def test_timeline_honors_from_to_window(db_session: Session) -> None:
    person = _seed_person(db_session)
    cam = _seed_camera(db_session)
    now = _utcnow().replace(microsecond=0)
    _seed_event(db_session, person.person_id, cam, now - timedelta(hours=2))
    _seed_event(db_session, person.person_id, cam, now - timedelta(minutes=30))

    frm = (now - timedelta(hours=1)).isoformat()
    to = now.isoformat()
    status, body = await _get(
        f"/api/persons/{person.person_id}/timeline?from={frm}&to={to}", db_session
    )

    assert status == 200
    assert len(body["spans"]) == 1
    assert body["spans"][0]["from_ts"] == (now - timedelta(minutes=30)).isoformat()


async def test_timeline_default_window_includes_recent_events(db_session: Session) -> None:
    person = _seed_person(db_session)
    cam = _seed_camera(db_session)
    _seed_event(db_session, person.person_id, cam, _utcnow() - timedelta(hours=1))

    status, body = await _get(f"/api/persons/{person.person_id}/timeline", db_session)

    assert status == 200
    assert len(body["spans"]) == 1


async def test_timeline_camera_and_zone_filters(db_session: Session) -> None:
    person = _seed_person(db_session)
    cam_a = _seed_camera(db_session)
    cam_b = _seed_camera(db_session)
    zone = _seed_zone(db_session)
    now = _utcnow() - timedelta(minutes=5)
    _seed_event(db_session, person.person_id, cam_a, now, zone_id=zone)
    _seed_event(db_session, person.person_id, cam_b, now)

    status, body = await _get(
        f"/api/persons/{person.person_id}/timeline?camera_id={cam_a}", db_session
    )
    assert status == 200
    assert len(body["spans"]) == 1
    assert body["spans"][0]["camera_id"] == cam_a

    status, body = await _get(
        f"/api/persons/{person.person_id}/timeline?zone_id={zone}", db_session
    )
    assert status == 200
    assert len(body["spans"]) == 1
    assert body["spans"][0]["zone_id"] == zone


async def test_timeline_limit_truncation_and_validation(db_session: Session) -> None:
    person = _seed_person(db_session)
    cam = _seed_camera(db_session)
    t0 = _utcnow().replace(microsecond=0) - timedelta(minutes=20)
    for i in range(3):  # 3 separate spans (distinct gids)
        _seed_event(db_session, person.person_id, cam, t0 + timedelta(seconds=i * 60))

    status, body = await _get(f"/api/persons/{person.person_id}/timeline?limit=2", db_session)
    assert status == 200
    assert len(body["spans"]) == 2
    assert body["truncated"] is True

    status, _ = await _get(f"/api/persons/{person.person_id}/timeline?limit=501", db_session)
    assert status == 422

    now = _utcnow().replace(microsecond=0)
    frm = now.isoformat()
    to = (now - timedelta(hours=1)).isoformat()
    status, _ = await _get(
        f"/api/persons/{person.person_id}/timeline?from={frm}&to={to}", db_session
    )
    assert status == 422


# -- authz --------------------------------------------------------------------


async def test_timeline_below_manager_returns_403(db_session: Session) -> None:
    person = _seed_person(db_session)
    status, _ = await _get(f"/api/persons/{person.person_id}/timeline", db_session, role="guard")
    assert status == 403


async def test_timeline_camera_permission_filters_rows(db_session: Session) -> None:
    person = _seed_person(db_session)
    cam_a = _seed_camera(db_session)
    cam_b = _seed_camera(db_session)
    now = _utcnow() - timedelta(minutes=5)
    _seed_event(db_session, person.person_id, cam_a, now)
    _seed_event(db_session, person.person_id, cam_b, now)

    scoped = User(username=f"mgr_{uuid.uuid4().hex[:8]}", password_hash="x", role="manager")
    db_session.add(scoped)
    db_session.flush()
    db_session.add(UserCameraPermission(user_id=scoped.user_id, camera_id=cam_a))
    db_session.flush()

    status, body = await _get(
        f"/api/persons/{person.person_id}/timeline", db_session, user_id=scoped.user_id
    )

    assert status == 200
    assert len(body["spans"]) == 1
    assert body["spans"][0]["camera_id"] == cam_a


async def test_timeline_manager_without_permission_rows_sees_all(db_session: Session) -> None:
    """No scoping rows configured for the user => unrestricted (current deployments)."""
    person = _seed_person(db_session)
    cam_a = _seed_camera(db_session)
    cam_b = _seed_camera(db_session)
    now = _utcnow() - timedelta(minutes=5)
    _seed_event(db_session, person.person_id, cam_a, now)
    _seed_event(db_session, person.person_id, cam_b, now)

    status, body = await _get(f"/api/persons/{person.person_id}/timeline", db_session)

    assert status == 200
    assert len(body["spans"]) == 2


# -- GDPR + audit -------------------------------------------------------------


async def test_timeline_purged_person_returns_empty_list(db_session: Session) -> None:
    person = _seed_person(db_session, purged=True)
    cam = _seed_camera(db_session)
    _seed_event(db_session, person.person_id, cam, _utcnow() - timedelta(minutes=5))

    status, body = await _get(f"/api/persons/{person.person_id}/timeline", db_session)

    assert status == 200
    assert body["spans"] == []
    assert body["truncated"] is False


async def test_timeline_absent_person_returns_404(db_session: Session) -> None:
    status, _ = await _get("/api/persons/999999/timeline", db_session)
    assert status == 404


async def test_timeline_writes_audit_event_and_chain_verifies(db_session: Session) -> None:
    person = _seed_person(db_session)
    cam = _seed_camera(db_session)
    _seed_event(db_session, person.person_id, cam, _utcnow() - timedelta(minutes=5))

    status, _ = await _get(f"/api/persons/{person.person_id}/timeline", db_session)
    assert status == 200

    rows = (
        db_session.execute(
            select(AuditLog).where(
                AuditLog.event_type == "PERSON_TIMELINE_QUERIED",
                AuditLog.target_id == str(person.person_id),
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]

    # Hash-chain linkage: row_hash recomputes from the stored fields + prev_hash.
    # (Scoped to this row — a full /api/audit/verify sweep is order-dependent in the
    # shared test DB because the audit tamper tests commit deliberately broken rows.)
    assert row.prev_hash is not None
    assert row.row_hash == compute_row_hash(
        audit_id=row.audit_id,
        event_type=row.event_type,
        actor_user_id=row.actor_user_id,
        target_type=row.target_type,
        target_id=row.target_id,
        payload=row.payload,
        prev_hash=row.prev_hash,
        event_ts=row.event_ts,
    )


# -- volume -------------------------------------------------------------------


@pytest.mark.integration
async def test_timeline_volume_50k_events_answers_under_budget(db_session: Session) -> None:
    person = _seed_person(db_session)
    cam = _seed_camera(db_session)
    now = _utcnow().replace(microsecond=0)

    rows = [
        {
            "camera_id": cam,
            "local_track_id": "t1",
            "global_track_id": uuid.uuid4(),  # each event its own span
            "person_id": person.person_id,
            "zone_id": None,
            "event_ts": now - timedelta(seconds=i),
            "ingest_ts": now - timedelta(seconds=i),
            "bbox_x1": 10,
            "bbox_y1": 10,
            "bbox_x2": 50,
            "bbox_y2": 90,
            "floor_x": None,
            "floor_y": None,
            "seq_id": i,
            "resolved_via": None,
        }
        for i in range(50_000)
    ]
    db_session.execute(TrackingEvent.__table__.insert(), rows)
    db_session.flush()

    started = time.perf_counter()
    status, body = await _get(f"/api/persons/{person.person_id}/timeline", db_session)
    elapsed = time.perf_counter() - started

    assert status == 200
    assert len(body["spans"]) == 500  # default max
    assert body["truncated"] is True
    assert elapsed < 0.5, f"timeline query took {elapsed:.3f}s (budget 0.5s)"
