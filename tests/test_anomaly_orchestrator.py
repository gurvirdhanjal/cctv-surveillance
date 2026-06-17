"""Tests for AnomalyOrchestrator."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fakeredis.aioredis import FakeRedis
from sqlalchemy.orm import Session

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    Severity,
)
from vms.anomaly.orchestrator import AnomalyOrchestrator
from vms.db.models import Alert, Camera
from vms.inference.messages import DetectionFrame, Tracklet


def _utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class _AlwaysFires(AnomalyDetector):
    alert_type = "UNKNOWN_PERSON"
    severity = Severity.HIGH
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL",)

    def should_run(self, ctx: DetectorContext) -> bool:
        return True

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        return AnomalyEvent(
            alert_type="UNKNOWN_PERSON",
            severity=Severity.HIGH,
            camera_id=ctx.frame.camera_id,
            zone_id=None,
            global_track_id=uuid.uuid4(),
            person_id=None,
            event_ts=_utc_naive(),
            dedup_key=f"UNKNOWN_PERSON:cam={ctx.frame.camera_id}:seq={ctx.frame.seq_id}",
        )

    def fsm_config(self) -> FSMConfig:
        return FSMConfig(sustain_ms=0, cooldown_ms=60_000, dedup_window_ms=60_000)


class _Raises(AnomalyDetector):
    alert_type = "INTRUSION"
    severity = Severity.CRITICAL
    requires_models: tuple[str, ...] = ()
    requires_tier: tuple[str, ...] = ("FULL",)

    def should_run(self, ctx: DetectorContext) -> bool:
        return True

    def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
        raise RuntimeError("intentional")

    def fsm_config(self) -> FSMConfig:
        return FSMConfig()


@pytest.mark.asyncio
async def test_process_frame_fires_one_alert(db_session: Session) -> None:
    cam = Camera(name="OrchC", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    client = FakeRedis(decode_responses=True)
    orch = AnomalyOrchestrator(
        redis_client=client,
        session_factory=lambda: db_session,
        detectors={"UNKNOWN_PERSON": _AlwaysFires({})},
    )
    frame = DetectionFrame(
        camera_id=cam.camera_id,
        seq_id=1,
        timestamp_ms=int(_utc_naive().timestamp() * 1000),
        tracklets=(
            Tracklet(
                local_track_id=1,
                camera_id=cam.camera_id,
                bbox=(0, 0, 10, 10),
                confidence=0.9,
            ),
        ),
        face_embeddings=(),
    )
    await orch.process_frame(frame)
    db_session.flush()
    assert db_session.query(Alert).filter_by(alert_type="UNKNOWN_PERSON").count() == 1


@pytest.mark.asyncio
async def test_failing_detector_does_not_kill_others(db_session: Session) -> None:
    cam = Camera(name="OrchC2", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    client = FakeRedis(decode_responses=True)
    orch = AnomalyOrchestrator(
        redis_client=client,
        session_factory=lambda: db_session,
        detectors={
            "INTRUSION": _Raises({}),
            "UNKNOWN_PERSON": _AlwaysFires({}),
        },
    )
    frame = DetectionFrame(
        camera_id=cam.camera_id,
        seq_id=1,
        timestamp_ms=int(_utc_naive().timestamp() * 1000),
        tracklets=(
            Tracklet(
                local_track_id=1,
                camera_id=cam.camera_id,
                bbox=(0, 0, 10, 10),
                confidence=0.9,
            ),
        ),
        face_embeddings=(),
    )
    await orch.process_frame(frame)
    db_session.flush()
    assert db_session.query(Alert).filter_by(alert_type="UNKNOWN_PERSON").count() == 1
    assert orch.health()["INTRUSION"]["consecutive_errors"] == 1


@pytest.mark.asyncio
async def test_detector_auto_disabled_after_max_consecutive_errors(db_session: Session) -> None:
    cam = Camera(name="OrchC3", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    client = FakeRedis(decode_responses=True)
    orch = AnomalyOrchestrator(
        redis_client=client,
        session_factory=lambda: db_session,
        detectors={"INTRUSION": _Raises({})},
        max_consecutive_errors=2,
    )
    frame = DetectionFrame(
        camera_id=cam.camera_id,
        seq_id=1,
        timestamp_ms=int(_utc_naive().timestamp() * 1000),
        tracklets=(),
        face_embeddings=(),
    )
    await orch.process_frame(frame)
    await orch.process_frame(frame)
    await orch.process_frame(frame)
    assert orch.health()["INTRUSION"]["disabled"] is True
