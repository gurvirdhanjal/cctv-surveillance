"""Tests for AlertFSM and the alerts stream publisher."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import redis.asyncio as aioredis
from sqlalchemy.orm import Session

from vms.anomaly.base import AnomalyEvent, FSMConfig, Severity
from vms.anomaly.fsm import AlertFSM, FSMDecision
from vms.anomaly.maintenance import MaintenanceCalendar
from vms.anomaly.streams import publish_alert_fired
from vms.db.models import Alert, Camera, MaintenanceWindow, User


def _utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ev(
    *,
    dedup: str = "k",
    ts: datetime | None = None,
    alert_type: str = "UNKNOWN_PERSON",
    camera_id: int = 1,
) -> AnomalyEvent:
    return AnomalyEvent(
        alert_type=alert_type,
        severity=Severity.HIGH,
        camera_id=camera_id,
        zone_id=None,
        global_track_id=uuid.uuid4(),
        person_id=None,
        event_ts=ts or _utc_naive(),
        dedup_key=dedup,
        payload={},
    )


@pytest.mark.asyncio
async def test_publish_alert_fired_writes_to_stream() -> None:
    from fakeredis.aioredis import FakeRedis

    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    msg_id = await publish_alert_fired(
        client,
        alert_id=42,
        alert_type="VIOLENCE",
        severity="CRITICAL",
        camera_id=7,
        zone_id=3,
        global_track_id=uuid.uuid4(),
        person_id=None,
        triggered_at=_utc_naive(),
    )
    assert msg_id
    raw = await client.xrange("alerts")
    assert len(raw) == 1
    _, fields = raw[0]
    body = json.loads(fields["payload"])
    assert body["alert_id"] == 42
    assert body["schema_version"] == "1"


def _seed_cam(db: Session, name: str = "FSMCam") -> int:
    c = Camera(name=name, rtsp_url="rtsp://x", capability_tier="FULL")
    db.add(c)
    db.flush()
    return c.camera_id


@pytest.mark.asyncio
async def test_first_event_below_sustain_does_not_fire(db_session: Session) -> None:
    cid = _seed_cam(db_session)
    cfg = FSMConfig(sustain_ms=500, cooldown_ms=60_000, dedup_window_ms=60_000)
    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis

    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)

    t0 = _utc_naive()
    dec = await fsm.process(_ev(dedup="k1", ts=t0, camera_id=cid), cfg)
    assert dec is FSMDecision.SUSTAINING


@pytest.mark.asyncio
async def test_sustained_event_fires_and_publishes(db_session: Session) -> None:
    cid = _seed_cam(db_session, name="FSMCam2")
    cfg = FSMConfig(sustain_ms=100, cooldown_ms=60_000, dedup_window_ms=60_000)
    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis

    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)

    t0 = _utc_naive()
    await fsm.process(_ev(dedup="k2", ts=t0, camera_id=cid), cfg)
    dec = await fsm.process(
        _ev(dedup="k2", ts=t0 + timedelta(milliseconds=150), camera_id=cid), cfg
    )
    assert dec is FSMDecision.FIRED

    db_session.flush()
    rows = db_session.query(Alert).filter_by(dedup_key="k2").all()
    assert len(rows) == 1
    assert rows[0].state == "active"

    raw = await client.xrange("alerts")
    assert len(raw) == 1


@pytest.mark.asyncio
async def test_duplicate_event_during_active_alert_is_deduped(db_session: Session) -> None:
    cid = _seed_cam(db_session, name="FSMCam3")
    cfg = FSMConfig(sustain_ms=0, cooldown_ms=60_000, dedup_window_ms=60_000)
    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis

    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)

    t0 = _utc_naive()
    await fsm.process(_ev(dedup="k3", ts=t0, camera_id=cid), cfg)
    db_session.flush()
    dec = await fsm.process(_ev(dedup="k3", ts=t0 + timedelta(seconds=2), camera_id=cid), cfg)
    assert dec is FSMDecision.DEDUPED
    assert db_session.query(Alert).filter_by(dedup_key="k3").count() == 1


@pytest.mark.asyncio
async def test_after_cooldown_a_new_alert_can_fire(db_session: Session) -> None:
    cid = _seed_cam(db_session, name="FSMCam4")
    cfg = FSMConfig(sustain_ms=0, cooldown_ms=1_000, dedup_window_ms=1_000)
    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis

    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)

    t0 = _utc_naive()
    await fsm.process(_ev(dedup="k4", ts=t0, camera_id=cid), cfg)
    db_session.flush()
    # mark first alert resolved so dedup window cleans up
    db_session.query(Alert).filter_by(dedup_key="k4").update(
        {"state": "resolved", "resolved_at": t0 + timedelta(seconds=2)}
    )
    db_session.flush()
    fsm.evict_closed(now=t0 + timedelta(seconds=5))

    dec = await fsm.process(_ev(dedup="k4", ts=t0 + timedelta(seconds=10), camera_id=cid), cfg)
    assert dec is FSMDecision.FIRED
    assert db_session.query(Alert).filter_by(dedup_key="k4").count() == 2


@pytest.mark.asyncio
async def test_maintenance_suppression_writes_suppressed_state(db_session: Session) -> None:
    cid = _seed_cam(db_session, name="FSMCam5")
    u = User(username="fsm_op", password_hash="x", role="admin", is_active=True)
    db_session.add(u)
    db_session.flush()
    now = _utc_naive()
    db_session.add(
        MaintenanceWindow(
            name="window",
            scope_type="CAMERA",
            scope_id=cid,
            schedule_type="ONE_TIME",
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(minutes=10),
            created_by=u.user_id,
        )
    )
    db_session.flush()

    cfg = FSMConfig(sustain_ms=0, cooldown_ms=60_000, dedup_window_ms=60_000)
    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis

    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)

    dec = await fsm.process(_ev(dedup="k5", ts=now, camera_id=cid), cfg)
    assert dec is FSMDecision.SUPPRESSED
    db_session.flush()
    row = db_session.query(Alert).filter_by(dedup_key="k5").one()
    assert row.state == "suppressed"
    assert row.suppressed_by_window_id is not None
    raw = await client.xrange("alerts")
    assert len(raw) == 0  # not published


@pytest.mark.asyncio
async def test_rebuild_active_from_db_on_construct(db_session: Session) -> None:
    cid = _seed_cam(db_session, name="FSMCam6")
    db_session.add(
        Alert(
            alert_type="UNKNOWN_PERSON",
            severity="HIGH",
            state="active",
            camera_id=cid,
            triggered_at=_utc_naive(),
            dedup_key="k6",
        )
    )
    db_session.flush()

    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis

    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)
    fsm.rebuild_from_db()
    cfg = FSMConfig(sustain_ms=0, cooldown_ms=60_000, dedup_window_ms=60_000)
    dec = await fsm.process(_ev(dedup="k6", ts=_utc_naive(), camera_id=cid), cfg)
    assert dec is FSMDecision.DEDUPED


@pytest.mark.asyncio
async def test_evict_closed_removes_resolved_entry_and_allows_new_fire(
    db_session: Session,
) -> None:
    cid = _seed_cam(db_session, name="FSMCam7")
    cfg = FSMConfig(sustain_ms=0, cooldown_ms=60_000, dedup_window_ms=60_000)
    cal = MaintenanceCalendar(session_factory=lambda: db_session)
    from fakeredis.aioredis import FakeRedis

    client: aioredis.Redis = FakeRedis(decode_responses=True)  # type: ignore[assignment]
    fsm = AlertFSM(redis_client=client, calendar=cal, session_factory=lambda: db_session)

    t0 = _utc_naive()
    await fsm.process(_ev(dedup="k7", ts=t0, camera_id=cid), cfg)
    db_session.flush()
    db_session.query(Alert).filter_by(dedup_key="k7").update(
        {"state": "resolved", "resolved_at": t0}
    )
    db_session.flush()

    evicted = fsm.evict_closed(now=t0)
    assert evicted == 1, "resolved alert entry must be evicted"

    dec = await fsm.process(_ev(dedup="k7", ts=t0, camera_id=cid), cfg)
    assert dec is FSMDecision.FIRED, "after eviction same key must fire again"
    assert db_session.query(Alert).filter_by(dedup_key="k7").count() == 2
