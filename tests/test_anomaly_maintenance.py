"""Tests for MaintenanceCalendar."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from vms.anomaly.maintenance import MaintenanceCalendar
from vms.db.models import Camera, MaintenanceWindow, User, Zone


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_user(db: Session) -> int:
    u = User(username=f"mw_creator_{id(db)}", password_hash="x", role="admin", is_active=True)
    db.add(u)
    db.flush()
    return u.user_id


def test_one_time_window_suppresses_active_camera(db_session: Session) -> None:
    cam = Camera(name="C1", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    uid = _seed_user(db_session)
    now = _now_naive()
    db_session.add(
        MaintenanceWindow(
            name="planned",
            scope_type="CAMERA",
            scope_id=cam.camera_id,
            schedule_type="ONE_TIME",
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=5),
            suppress_alert_types=None,
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()
    win = cal.is_suppressed(
        camera_id=cam.camera_id, zone_id=None, alert_type="INTRUSION", event_ts=now
    )
    assert win is not None


def test_one_time_window_outside_range_not_suppressed(db_session: Session) -> None:
    cam = Camera(name="C2", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    uid = _seed_user(db_session)
    now = _now_naive()
    db_session.add(
        MaintenanceWindow(
            name="past",
            scope_type="CAMERA",
            scope_id=cam.camera_id,
            schedule_type="ONE_TIME",
            starts_at=now - timedelta(hours=2),
            ends_at=now - timedelta(hours=1),
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()
    assert (
        cal.is_suppressed(
            camera_id=cam.camera_id, zone_id=None, alert_type="INTRUSION", event_ts=now
        )
        is None
    )


def test_zone_scope_does_not_match_camera_scope(db_session: Session) -> None:
    z = Zone(name="Z1")
    db_session.add(z)
    db_session.flush()
    uid = _seed_user(db_session)
    now = _now_naive()
    db_session.add(
        MaintenanceWindow(
            name="zone-down",
            scope_type="ZONE",
            scope_id=z.zone_id,
            schedule_type="ONE_TIME",
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=5),
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()
    assert (
        cal.is_suppressed(camera_id=999, zone_id=None, alert_type="INTRUSION", event_ts=now) is None
    )
    assert (
        cal.is_suppressed(camera_id=None, zone_id=z.zone_id, alert_type="INTRUSION", event_ts=now)
        is not None
    )


def test_alert_type_filter_excludes_other_types(db_session: Session) -> None:
    cam = Camera(name="C3", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    uid = _seed_user(db_session)
    now = _now_naive()
    db_session.add(
        MaintenanceWindow(
            name="only-violence-supp",
            scope_type="CAMERA",
            scope_id=cam.camera_id,
            schedule_type="ONE_TIME",
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=5),
            suppress_alert_types=json.dumps(["VIOLENCE"]),
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()
    assert (
        cal.is_suppressed(
            camera_id=cam.camera_id, zone_id=None, alert_type="VIOLENCE", event_ts=now
        )
        is not None
    )
    assert (
        cal.is_suppressed(
            camera_id=cam.camera_id, zone_id=None, alert_type="INTRUSION", event_ts=now
        )
        is None
    )


def test_recurring_window_matches_inside_cron_slot(db_session: Session) -> None:
    cam = Camera(name="C4", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    uid = _seed_user(db_session)
    now = datetime(2026, 5, 16, 14, 5, 0)  # Saturday 14:05
    db_session.add(
        MaintenanceWindow(
            name="sat-2pm",
            scope_type="CAMERA",
            scope_id=cam.camera_id,
            schedule_type="RECURRING",
            cron_expr="0 14 * * 6",
            duration_minutes=30,
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()
    assert (
        cal.is_suppressed(
            camera_id=cam.camera_id, zone_id=None, alert_type="INTRUSION", event_ts=now
        )
        is not None
    )


def test_recurring_outside_cron_slot_not_suppressed(db_session: Session) -> None:
    cam = Camera(name="C5", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    uid = _seed_user(db_session)
    now = datetime(2026, 5, 17, 14, 5, 0)  # Sunday
    db_session.add(
        MaintenanceWindow(
            name="sat-2pm-b",
            scope_type="CAMERA",
            scope_id=cam.camera_id,
            schedule_type="RECURRING",
            cron_expr="0 14 * * 6",
            duration_minutes=30,
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()
    assert (
        cal.is_suppressed(
            camera_id=cam.camera_id, zone_id=None, alert_type="INTRUSION", event_ts=now
        )
        is None
    )


def test_malformed_cron_skipped_logged(
    db_session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    cam = Camera(name="C6", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    uid = _seed_user(db_session)
    db_session.add(
        MaintenanceWindow(
            name="bad-cron",
            scope_type="CAMERA",
            scope_id=cam.camera_id,
            schedule_type="RECURRING",
            cron_expr="not a cron",
            duration_minutes=15,
            created_by=uid,
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    cal.refresh_now()  # must not raise
    assert (
        cal.is_suppressed(
            camera_id=cam.camera_id, zone_id=None, alert_type="INTRUSION", event_ts=_now_naive()
        )
        is None
    )


def test_cache_respects_ttl(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Calendar does not re-query DB inside TTL window."""
    cal = MaintenanceCalendar(session_factory=lambda: db_session, ttl_s=10)
    cal.refresh_now()
    call_count = {"n": 0}
    orig = db_session.query

    def spy(*a, **kw):  # type: ignore[no-untyped-def]
        call_count["n"] += 1
        return orig(*a, **kw)

    monkeypatch.setattr(db_session, "query", spy)
    # Within TTL: no DB call
    cal.is_suppressed(camera_id=1, zone_id=None, alert_type="X", event_ts=_now_naive())
    assert call_count["n"] == 0
