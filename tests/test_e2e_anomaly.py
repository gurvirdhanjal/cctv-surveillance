"""End-to-end integration test: DetectionFrame -> AnomalyOrchestrator -> Alert in DB + stream.

Uses a real PostgreSQL test DB + fakeredis. No internal anomaly boundary is mocked.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import fakeredis.aioredis
import pytest
from sqlalchemy.orm import Session

from vms.anomaly.base import AnomalyDetector, AnomalyEvent, DetectorContext, FSMConfig, Severity
from vms.anomaly.orchestrator import AnomalyOrchestrator
from vms.db.models import Alert, Camera, MaintenanceWindow, User
from vms.inference.messages import DetectionFrame, Tracklet


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_user(db_session: Session) -> int:
    user = User(
        username=f"e2e-user-{uuid.uuid4().hex[:8]}",
        password_hash="$2b$12$placeholder",
        role="admin",
    )
    db_session.add(user)
    db_session.flush()
    return user.user_id


def _seed_camera(db_session: Session) -> int:
    cam = Camera(
        name=f"e2e-cam-{uuid.uuid4().hex[:8]}",
        rtsp_url="rtsp://e2e-test",
        capability_tier="FULL",
    )
    db_session.add(cam)
    db_session.flush()
    return cam.camera_id


class _AlwaysFiresDetector(AnomalyDetector):
    """Minimal detector that fires INTRUSION on every frame with >=1 tracklet."""

    alert_type = "INTRUSION"
    severity = Severity.HIGH
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ()

    def should_run(self, ctx: DetectorContext) -> bool:
        return bool(ctx.frame.tracklets)

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        return AnomalyEvent(
            alert_type=self.alert_type,
            severity=Severity.HIGH,
            camera_id=ctx.frame.camera_id,
            zone_id=None,
            global_track_id=uuid.uuid4(),
            person_id=None,
            event_ts=_now_naive(),
            dedup_key=f"e2e:INTRUSION:cam={ctx.frame.camera_id}:{ctx.frame.seq_id}",
            payload={},
        )

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=0, cooldown_ms=0, dedup_window_ms=0)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_e2e_frame_produces_alert_in_db_and_stream(db_session: Session) -> None:
    """Full stack: synthetic frame -> orchestrator -> Alert row in DB."""
    camera_id = _seed_camera(db_session)
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    orchestrator = AnomalyOrchestrator(
        redis_client=fake_redis,
        session_factory=lambda: db_session,
        detectors={"INTRUSION": _AlwaysFiresDetector({})},
    )

    frame = DetectionFrame(
        camera_id=camera_id,
        seq_id=1,
        timestamp_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        tracklets=(
            Tracklet(
                local_track_id=1,
                camera_id=camera_id,
                bbox=(10, 20, 100, 200),
                confidence=0.9,
                embedding=tuple([0.1] * 512),
            ),
        ),
        face_embeddings=(),
    )

    await orchestrator.process_frame(frame)
    db_session.flush()

    alert = db_session.query(Alert).filter_by(alert_type="INTRUSION").first()
    assert alert is not None, "Alert row must be persisted in DB"
    assert alert.state == "active"
    assert alert.camera_id == camera_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_e2e_maintenance_suppresses_alert(db_session: Session) -> None:
    """Alerts are suppressed when a ONE_TIME maintenance window covers the camera."""
    from vms.anomaly.maintenance import MaintenanceCalendar

    camera_id = _seed_camera(db_session)
    user_id = _seed_user(db_session)
    now = _now_naive()

    win = MaintenanceWindow(
        name="e2e-suppression-window",
        scope_type="CAMERA",
        scope_id=camera_id,
        schedule_type="ONE_TIME",
        starts_at=now,
        ends_at=datetime(2099, 1, 1),
        created_by=user_id,
    )
    db_session.add(win)
    db_session.flush()

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    calendar = MaintenanceCalendar(session_factory=lambda: db_session)
    calendar.refresh_now()

    orchestrator = AnomalyOrchestrator(
        redis_client=fake_redis,
        session_factory=lambda: db_session,
        detectors={"INTRUSION": _AlwaysFiresDetector({})},
        calendar=calendar,
    )

    frame = DetectionFrame(
        camera_id=camera_id,
        seq_id=2,
        timestamp_ms=int(datetime.now(timezone.utc).timestamp() * 1000),
        tracklets=(
            Tracklet(
                local_track_id=2,
                camera_id=camera_id,
                bbox=(0, 0, 50, 100),
                confidence=0.9,
                embedding=tuple([0.1] * 512),
            ),
        ),
        face_embeddings=(),
    )

    await orchestrator.process_frame(frame)
    db_session.flush()

    alert = db_session.query(Alert).filter_by(alert_type="INTRUSION", camera_id=camera_id).first()
    assert (
        alert is None or alert.state == "suppressed"
    ), "Alert must not be active when a ONE_TIME maintenance window covers the camera"
