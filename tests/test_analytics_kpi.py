"""Tests for GET /api/analytics/kpi (Phase 4P Task 3)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db
from vms.api.main import app
from vms.api.routes.state import set_head_count_aggregator
from vms.db.models import (
    Alert,
    AnalyticsHeadCountHourly,
    Camera,
    CameraStatusEvent,
    TrackingEvent,
)
from vms.identity.head_count import HeadCountAggregator


def _auth(role: str = "manager") -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hour_floor(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _seed_camera(db: Session) -> int:
    cam = Camera(name=f"KPI_{uuid.uuid4().hex[:6]}", rtsp_url="rtsp://x", capability_tier="FULL")
    db.add(cam)
    db.flush()
    return cam.camera_id


def _seed_alert(
    db: Session,
    camera_id: int,
    alert_type: str = "UNKNOWN_PERSON",
    severity: str = "HIGH",
    state: str = "active",
    triggered_at: datetime | None = None,
) -> None:
    db.add(
        Alert(
            alert_type=alert_type,
            severity=severity,
            state=state,
            camera_id=camera_id,
            triggered_at=triggered_at or _utcnow(),
            dedup_key=f"kpi:{uuid.uuid4().hex[:12]}",
        )
    )
    db.flush()


def _seed_event(db: Session, camera_id: int, ts: datetime, gid: uuid.UUID) -> None:
    db.add(
        TrackingEvent(
            camera_id=camera_id,
            local_track_id=f"t{uuid.uuid4().hex[:6]}",
            global_track_id=gid,
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


async def _get(path: str, db: Session, role: str = "manager") -> tuple[int, Any]:
    app.dependency_overrides[get_db] = lambda: db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(path, headers=_auth(role))
    finally:
        app.dependency_overrides.clear()
    return resp.status_code, (resp.json() if resp.content else {})


async def test_kpi_full_schema_with_seeded_data(db_session: Session) -> None:
    # Explicit 3h window in the past so live tests/alerts near "now" can't pollute it.
    # Sub-hour offset makes the window (= Redis cache key) unique per run — an
    # hour-aligned window would serve a stale cached body on re-runs within the TTL.
    now = _utcnow()
    b1 = _hour_floor(now - timedelta(hours=5)) + timedelta(
        seconds=now.second, microseconds=now.microsecond
    )
    b2 = b1 + timedelta(hours=1)
    window_from = b1
    window_to = b1 + timedelta(hours=3)

    # head-count rollup rows: peak 9 at b2
    db_session.add(AnalyticsHeadCountHourly(bucket_start=b1, zone_id=None, count=5))
    db_session.add(AnalyticsHeadCountHourly(bucket_start=b2, zone_id=None, count=9))
    db_session.flush()

    # dwell: gid1 spans 10 min, gid2 spans 20 min -> avg 15.0
    cam = _seed_camera(db_session)
    gid1, gid2 = uuid.uuid4(), uuid.uuid4()
    _seed_event(db_session, cam, window_from + timedelta(minutes=10), gid1)
    _seed_event(db_session, cam, window_from + timedelta(minutes=20), gid1)
    _seed_event(db_session, cam, window_from + timedelta(minutes=30), gid2)
    _seed_event(db_session, cam, window_from + timedelta(minutes=50), gid2)

    # unknown-person alerts: 2 inside the window, 1 outside
    _seed_alert(db_session, cam, triggered_at=window_from + timedelta(minutes=5))
    _seed_alert(db_session, cam, triggered_at=window_from + timedelta(minutes=6))
    _seed_alert(db_session, cam, triggered_at=window_from - timedelta(hours=1))

    # uptime: this camera offline for 15 min of the 3h window
    db_session.add(
        CameraStatusEvent(camera_id=cam, status="offline", at=window_from + timedelta(minutes=15))
    )
    db_session.add(
        CameraStatusEvent(camera_id=cam, status="online", at=window_from + timedelta(minutes=30))
    )
    db_session.flush()

    # open alerts: one acknowledged CRITICAL on top of the seeds above
    _seed_alert(db_session, cam, alert_type="INTRUSION", severity="CRITICAL", state="acknowledged")
    _seed_alert(db_session, cam, alert_type="LOITERING", severity="LOW", state="resolved")

    status, body = await _get(
        f"/api/analytics/kpi?from={window_from.isoformat()}&to={window_to.isoformat()}",
        db_session,
    )

    assert status == 200
    assert body["head_count_peak"] == 9
    assert body["head_count_peak_at"] == b2.isoformat()
    assert body["avg_dwell_minutes"] == 15.0
    assert body["unknown_person_events"] == 2

    # dynamic expectations — the shared test DB may hold committed rows from other tests
    n_cams: int = db_session.execute(select(func.count()).select_from(Camera)).scalar_one()
    expected_uptime = round(100.0 * ((n_cams - 1) * 1.0 + (1.0 - 900.0 / 10800.0)) / n_cams, 2)
    assert body["camera_uptime_pct"] == expected_uptime

    expected_open: int = db_session.execute(
        select(func.count()).select_from(Alert).where(Alert.state.in_(("active", "acknowledged")))
    ).scalar_one()
    assert body["open_alerts"] == expected_open
    assert sum(body["alerts_by_severity"].values()) == expected_open


async def test_kpi_default_window_returns_schema(db_session: Session) -> None:
    status, body = await _get("/api/analytics/kpi", db_session)

    assert status == 200
    for key in (
        "head_count_peak",
        "head_count_peak_at",
        "avg_dwell_minutes",
        "unknown_person_events",
        "camera_uptime_pct",
        "open_alerts",
        "alerts_by_severity",
    ):
        assert key in body


async def test_kpi_live_topup_from_head_count_aggregator(db_session: Session) -> None:
    agg = HeadCountAggregator()
    now = _utcnow()
    for _ in range(3):
        agg.on_tracking_event(uuid.uuid4(), zone_id=1, ts=now)
    set_head_count_aggregator(agg)
    try:
        status, body = await _get("/api/analytics/kpi", db_session)
    finally:
        set_head_count_aggregator(None)  # type: ignore[arg-type]

    assert status == 200
    assert body["head_count_peak"] >= 3


async def test_kpi_from_after_to_returns_422(db_session: Session) -> None:
    now = _utcnow()
    frm = now.isoformat()
    to = (now - timedelta(hours=1)).isoformat()
    status, _ = await _get(f"/api/analytics/kpi?from={frm}&to={to}", db_session)
    assert status == 422


async def test_kpi_below_manager_returns_403(db_session: Session) -> None:
    status, _ = await _get("/api/analytics/kpi", db_session, role="guard")
    assert status == 403


async def test_kpi_survives_redis_down(db_session: Session, monkeypatch: Any) -> None:
    import vms.api.routes.analytics as analytics_module

    def _boom() -> Any:
        raise ConnectionError("redis down")

    monkeypatch.setattr(analytics_module, "get_api_redis", _boom)

    status, body = await _get("/api/analytics/kpi", db_session)

    assert status == 200
    assert "head_count_peak" in body


async def test_kpi_result_cached_in_redis(db_session: Session) -> None:
    import redis as sync_redis

    window_from = (_utcnow() - timedelta(hours=8)).replace(microsecond=123456)
    window_to = window_from + timedelta(hours=1)

    status, _ = await _get(
        f"/api/analytics/kpi?from={window_from.isoformat()}&to={window_to.isoformat()}",
        db_session,
    )
    assert status == 200

    r = sync_redis.from_url("redis://localhost:6379/0")  # type: ignore[no-untyped-call]
    key = f"analytics:kpi:{window_from.isoformat()}:{window_to.isoformat()}"
    try:
        assert r.exists(key) == 1
        ttl = r.ttl(key)
        assert 0 < ttl <= 60
    finally:
        r.delete(key)
        r.close()
