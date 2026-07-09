"""Tests for head-count rollup + GET /api/analytics/head-count (Phase 4P Task 4)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.db.analytics_rollup import backfill_missed_hours, rollup_head_count_hour
from vms.db.models import AnalyticsHeadCountHourly, Camera, TrackingEvent
from vms.scheduler.jobs import JOBS


def _auth(role: str = "manager") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hour_floor(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _seed_camera(db: Session) -> int:
    cam = Camera(name=f"HC_{uuid.uuid4().hex[:6]}", rtsp_url="rtsp://x", capability_tier="FULL")
    db.add(cam)
    db.flush()
    return cam.camera_id


def _seed_event(
    db: Session,
    camera_id: int,
    ts: datetime,
    gid: uuid.UUID,
    person_id: int | None = None,
    zone_id: int | None = None,
) -> None:
    db.add(
        TrackingEvent(
            camera_id=camera_id,
            local_track_id=f"t{uuid.uuid4().hex[:6]}",
            global_track_id=gid,
            person_id=person_id,
            zone_id=zone_id,
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


def _rollup_rows(db: Session) -> list[AnalyticsHeadCountHourly]:
    return list(
        db.execute(
            select(AnalyticsHeadCountHourly).order_by(
                AnalyticsHeadCountHourly.bucket_start, AnalyticsHeadCountHourly.zone_id
            )
        )
        .scalars()
        .all()
    )


# -- rollup -------------------------------------------------------------------


def test_rollup_hour_dedups_persons_and_counts_zones(db_session: Session) -> None:
    """Identified persons dedup by person_id across tracks; unknowns dedup by gid."""
    from vms.db.models import Person

    person = Person(name="HC Person", employee_id=f"E{uuid.uuid4().hex[:8]}")
    db_session.add(person)
    db_session.flush()

    cam = _seed_camera(db_session)
    bucket = _hour_floor(_utcnow() - timedelta(hours=1))
    # same person seen on two different tracks in two zones -> 1 in plant, 1 per zone
    _seed_event(db_session, cam, bucket + timedelta(minutes=5), uuid.uuid4(), person.person_id, 1)
    _seed_event(db_session, cam, bucket + timedelta(minutes=40), uuid.uuid4(), person.person_id, 2)
    # one unknown (gid-only) in zone 1
    _seed_event(db_session, cam, bucket + timedelta(minutes=10), uuid.uuid4(), None, 1)
    # event outside the bucket -> ignored
    _seed_event(db_session, cam, bucket + timedelta(hours=1, minutes=1), uuid.uuid4(), None, 1)

    rollup_head_count_hour(db_session, bucket)
    db_session.flush()

    rows = {(r.bucket_start, r.zone_id): r.count for r in _rollup_rows(db_session)}
    assert rows[(bucket, None)] == 2  # plant: person (deduped) + unknown
    assert rows[(bucket, 1)] == 2  # zone 1: person + unknown
    assert rows[(bucket, 2)] == 1  # zone 2: person only


def test_rollup_hour_is_idempotent(db_session: Session) -> None:
    cam = _seed_camera(db_session)
    bucket = _hour_floor(_utcnow() - timedelta(hours=1))
    _seed_event(db_session, cam, bucket + timedelta(minutes=5), uuid.uuid4(), None, 3)

    rollup_head_count_hour(db_session, bucket)
    db_session.flush()
    rollup_head_count_hour(db_session, bucket)
    db_session.flush()

    rows = _rollup_rows(db_session)
    assert len(rows) == 2  # plant row + zone-3 row, no duplicates
    assert {(r.zone_id, r.count) for r in rows} == {(None, 1), (3, 1)}


def test_rollup_hour_with_no_events_writes_zero_plant_row(db_session: Session) -> None:
    bucket = _hour_floor(_utcnow() - timedelta(hours=1))

    rollup_head_count_hour(db_session, bucket)
    db_session.flush()

    rows = _rollup_rows(db_session)
    assert [(r.zone_id, r.count) for r in rows] == [(None, 0)]


def test_backfill_fills_missed_closed_hours_bounded(db_session: Session) -> None:
    cam = _seed_camera(db_session)
    now = _utcnow()
    seeded_bucket = _hour_floor(now - timedelta(hours=2))
    _seed_event(db_session, cam, seeded_bucket + timedelta(minutes=5), uuid.uuid4(), None, None)

    created = backfill_missed_hours(db_session, now=now)
    db_session.flush()

    from vms.config import get_settings

    max_hours = get_settings().rollup_backfill_max_hours
    assert created == max_hours
    plant = {r.bucket_start: r.count for r in _rollup_rows(db_session) if r.zone_id is None}
    assert len(plant) == max_hours
    assert plant[seeded_bucket] == 1
    # last closed hour present; current (open) hour absent
    assert _hour_floor(now) - timedelta(hours=1) in plant
    assert _hour_floor(now) not in plant

    # second run: nothing new to do
    assert backfill_missed_hours(db_session, now=now) == 0


def test_head_count_rollup_job_registered() -> None:
    assert any(j.name == "head_count_rollup" for j in JOBS)


# -- endpoint -----------------------------------------------------------------


def _seed_rollup(db: Session, bucket: datetime, zone_id: int | None, count: int) -> None:
    db.add(AnalyticsHeadCountHourly(bucket_start=bucket, zone_id=zone_id, count=count))
    db.flush()


async def _get(path: str, db: Session, role: str = "manager") -> tuple[int, dict]:  # type: ignore[type-arg]
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(path, headers=_auth(role))
    finally:
        app.dependency_overrides.clear()
    return resp.status_code, (resp.json() if resp.content else {})


async def test_head_count_series_hourly(db_session: Session) -> None:
    h1 = _hour_floor(_utcnow() - timedelta(hours=2))
    h2 = h1 + timedelta(hours=1)
    _seed_rollup(db_session, h1, None, 5)
    _seed_rollup(db_session, h1, 7, 3)
    _seed_rollup(db_session, h2, None, 8)

    status, body = await _get("/api/analytics/head-count?days=1&bucket=hour", db_session)

    assert status == 200
    series = body["series"]
    assert [p["plant_total"] for p in series] == [5, 8]
    assert series[0]["ts"] == h1.isoformat()
    assert series[0]["by_zone"] == {"7": 3}
    assert series[1]["by_zone"] == {}


async def test_head_count_series_day_bucket_sums_hours(db_session: Session) -> None:
    now = _utcnow()
    h1 = _hour_floor(now - timedelta(hours=3))
    h2 = _hour_floor(now - timedelta(hours=2))
    _seed_rollup(db_session, h1, None, 5)
    _seed_rollup(db_session, h2, None, 8)
    _seed_rollup(db_session, h2, 4, 2)

    status, body = await _get("/api/analytics/head-count?days=2&bucket=day", db_session)

    assert status == 200
    totals = {p["ts"]: p["plant_total"] for p in body["series"]}
    # h1/h2 may straddle midnight; sum across returned days must equal 13
    assert sum(totals.values()) == 13
    all_zone_sums: dict[str, int] = {}
    for p in body["series"]:
        for z, n in p["by_zone"].items():
            all_zone_sums[z] = all_zone_sums.get(z, 0) + n
    assert all_zone_sums == {"4": 2}


async def test_head_count_days_over_90_returns_422(db_session: Session) -> None:
    status, _ = await _get("/api/analytics/head-count?days=91", db_session)
    assert status == 422


async def test_head_count_below_manager_returns_403(db_session: Session) -> None:
    status, _ = await _get("/api/analytics/head-count?days=1", db_session, role="guard")
    assert status == 403


async def test_head_count_unauthenticated_returns_401(db_session: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/analytics/head-count?days=1")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 401
