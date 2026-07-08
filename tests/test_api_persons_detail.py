"""Tests for GET /api/persons/{person_id} (Phase 4P Task 1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.db.models import Camera, Person, PersonEmbedding, TrackingEvent


def _auth(role: str = "manager") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_person(
    db: Session,
    name: str = "Brijesh Kumar",
    thumbnail_path: str | None = None,
    purged: bool = False,
) -> Person:
    person = Person(
        name=name,
        employee_id=f"E{uuid.uuid4().hex[:8]}",
        thumbnail_path=thumbnail_path,
    )
    if purged:
        person.is_active = False
        person.purged_at = _utcnow()
    db.add(person)
    db.flush()
    return person


def _seed_camera(db: Session) -> int:
    cam = Camera(name=f"PD_{uuid.uuid4().hex[:6]}", rtsp_url="rtsp://x", capability_tier="FULL")
    db.add(cam)
    db.flush()
    return cam.camera_id


def _seed_embedding(db: Session, person_id: int) -> None:
    db.add(PersonEmbedding(person_id=person_id, embedding=[0.0] * 512, quality_score=0.9))
    db.flush()


def _seed_event(
    db: Session,
    person_id: int | None,
    camera_id: int,
    ts: datetime,
    track: str = "t1",
) -> None:
    db.add(
        TrackingEvent(
            camera_id=camera_id,
            local_track_id=track,
            global_track_id=uuid.uuid4(),
            person_id=person_id,
            event_ts=ts,
            ingest_ts=ts,
            bbox_x1=10,
            bbox_y1=10,
            bbox_x2=50,
            bbox_y2=90,
            seq_id=1,
        )
    )
    db.flush()


async def _get(path: str, db: Session, role: str = "manager") -> tuple[int, dict]:  # type: ignore[type-arg]
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(path, headers=_auth(role))
    finally:
        app.dependency_overrides.clear()
    return resp.status_code, (resp.json() if resp.content else {})


async def test_person_detail_returns_full_schema_with_last_seen(db_session: Session) -> None:
    person = _seed_person(db_session)
    _seed_embedding(db_session, person.person_id)
    _seed_embedding(db_session, person.person_id)
    cam_a = _seed_camera(db_session)
    cam_b = _seed_camera(db_session)
    now = _utcnow().replace(microsecond=0)
    _seed_event(db_session, person.person_id, cam_a, now - timedelta(minutes=10))
    _seed_event(db_session, person.person_id, cam_b, now)

    status, body = await _get(f"/api/persons/{person.person_id}", db_session)

    assert status == 200
    assert body["person_id"] == person.person_id
    assert body["full_name"] == "Brijesh Kumar"
    assert body["role"] is None
    assert body["created_at"] is not None
    assert body["embedding_count"] == 2
    assert body["last_seen_at"] == now.isoformat()
    assert body["last_seen_camera_id"] == cam_b
    assert body["thumbnail_url"] is None


async def test_person_detail_thumbnail_url_prefixed_with_media(db_session: Session) -> None:
    person = _seed_person(db_session, thumbnail_path="thumbs/p1.jpg")

    status, body = await _get(f"/api/persons/{person.person_id}", db_session)

    assert status == 200
    assert body["thumbnail_url"] == "/media/thumbs/p1.jpg"


async def test_person_detail_without_sightings_has_null_last_seen(db_session: Session) -> None:
    person = _seed_person(db_session)

    status, body = await _get(f"/api/persons/{person.person_id}", db_session)

    assert status == 200
    assert body["embedding_count"] == 0
    assert body["last_seen_at"] is None
    assert body["last_seen_camera_id"] is None


async def test_person_detail_absent_returns_404(db_session: Session) -> None:
    status, _ = await _get("/api/persons/999999", db_session)
    assert status == 404


async def test_person_detail_purged_returns_404(db_session: Session) -> None:
    person = _seed_person(db_session, purged=True)
    status, _ = await _get(f"/api/persons/{person.person_id}", db_session)
    assert status == 404


async def test_person_detail_below_manager_returns_403(db_session: Session) -> None:
    person = _seed_person(db_session)
    status, _ = await _get(f"/api/persons/{person.person_id}", db_session, role="guard")
    assert status == 403


async def test_person_detail_unauthenticated_returns_401(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/persons/1")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 401


async def test_persons_search_still_resolves_after_detail_route(db_session: Session) -> None:
    """Regression guard: /api/persons/search must not be shadowed by /persons/{person_id}."""
    _seed_person(db_session, name="Searchable Sam")

    status, body = await _get("/api/persons/search?q=Searchable", db_session)

    assert status == 200
    assert isinstance(body, list)
    assert any("Searchable" in p["name"] for p in body)
