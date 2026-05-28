"""Tests for the AnomalyDetector ABC + DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from vms.anomaly.base import (
    AnomalyDetector,
    AnomalyEvent,
    DetectorContext,
    FSMConfig,
    Severity,
)
from vms.inference.messages import DetectionFrame


def _empty_frame(camera_id: int = 1) -> DetectionFrame:
    return DetectionFrame(
        camera_id=camera_id,
        seq_id=1,
        timestamp_ms=1_700_000_000_000,
        tracklets=(),
        face_embeddings=(),
    )


def test_severity_enum_values() -> None:
    assert Severity.LOW.value == "LOW"
    assert Severity.CRITICAL.value == "CRITICAL"


def test_fsm_config_defaults() -> None:
    cfg = FSMConfig()
    assert cfg.sustain_ms == 500
    assert cfg.cooldown_ms == 60_000
    assert cfg.dedup_window_ms == 60_000


def test_anomaly_event_is_frozen() -> None:
    ev = AnomalyEvent(
        alert_type="UNKNOWN_PERSON",
        severity=Severity.HIGH,
        camera_id=1,
        zone_id=2,
        global_track_id=uuid.uuid4(),
        person_id=None,
        event_ts=datetime.now(timezone.utc).replace(tzinfo=None),
        dedup_key="UNKNOWN_PERSON:zone=2:track=abc",
        payload={"confidence": 0.95},
    )
    with pytest.raises((AttributeError, TypeError)):
        ev.alert_type = "VIOLENCE"  # type: ignore[misc]


def test_detector_context_has_required_fields() -> None:
    ctx = DetectorContext(
        frame=_empty_frame(),
        zone_lookup={},
        active_track_zones={},
        head_count={},
        violence_score=None,
    )
    assert ctx.frame.camera_id == 1
    assert ctx.head_count == {}


def test_concrete_detector_cannot_skip_abstract_methods() -> None:
    class Bad(AnomalyDetector):
        alert_type = "X"
        severity = Severity.LOW
        requires_models: tuple[str, ...] = ()
        requires_tier: tuple[str, ...] = ("FULL",)

    with pytest.raises(TypeError):
        Bad({})  # cannot instantiate — missing abstract methods


def test_concrete_detector_passes_smoke() -> None:
    class Echo(AnomalyDetector):
        alert_type = "UNKNOWN_PERSON"
        severity = Severity.HIGH
        requires_models: tuple[str, ...] = ()
        requires_tier: tuple[str, ...] = ("FULL",)

        def should_run(self, ctx: DetectorContext) -> bool:
            return True

        def evaluate(self, ctx: DetectorContext) -> AnomalyEvent | None:
            return None

        def fsm_config(self) -> FSMConfig:
            return FSMConfig()

    d = Echo({})
    ctx = DetectorContext(
        frame=_empty_frame(),
        zone_lookup={},
        active_track_zones={},
        head_count={},
        violence_score=None,
    )
    assert d.should_run(ctx) is True
    assert d.evaluate(ctx) is None
