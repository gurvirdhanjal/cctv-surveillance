"""Tests for vms.config.Settings."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from vms.config import Settings, get_settings


def test_settings_load_from_env() -> None:
    s = Settings()
    assert "postgresql" in s.db_url
    assert s.redis_url == "redis://localhost:6379/0"
    assert s.jwt_secret == "test-secret-do-not-use"


def test_inference_threshold_defaults() -> None:
    s = Settings()
    assert s.scrfd_conf == 0.60
    assert s.adaface_min_sim == 0.72
    assert s.reid_cross_cam_sim == 0.65
    assert s.reid_margin == 0.08
    assert s.min_blur == 25.0
    assert s.min_face_px == 40


def test_pipeline_tuning_defaults() -> None:
    s = Settings()
    assert s.stale_threshold_ms == 200
    assert s.db_flush_rows == 100
    assert s.db_flush_ms == 500
    assert s.redis_stream_maxlen == 500


def test_get_settings_is_cached() -> None:
    a = get_settings()
    b = get_settings()
    assert a is b


def test_missing_required_raises() -> None:
    from pydantic_core import ValidationError

    with patch.dict(os.environ, {}, clear=True), pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_reid_stale_ms_default() -> None:
    s = Settings(db_url="postgresql://x/y", jwt_secret="s")  # type: ignore[call-arg]
    assert s.reid_stale_ms == 300_000


def test_zone_cache_ttl_s_default() -> None:
    s = Settings(db_url="postgresql://x/y", jwt_secret="s")  # type: ignore[call-arg]
    assert s.zone_cache_ttl_s == 30


def test_storage_backend_defaults_to_local() -> None:
    s = Settings(db_url="postgresql://x/y", jwt_secret="s")  # type: ignore[call-arg]
    assert s.storage_backend == "local"


def test_storage_local_dir_defaults() -> None:
    s = Settings(db_url="postgresql://x/y", jwt_secret="s")  # type: ignore[call-arg]
    assert s.storage_local_dir == "thumbnails"


def test_minio_settings_default_empty() -> None:
    s = Settings(db_url="postgresql://x/y", jwt_secret="s")  # type: ignore[call-arg]
    assert s.minio_endpoint == ""
    assert s.minio_access_key == ""
    assert s.minio_secret_key == ""
    assert s.minio_bucket == "vms-media"


def test_anomaly_defaults() -> None:
    s = Settings(db_url="postgresql://x/y", jwt_secret="s")  # type: ignore[call-arg]
    # violence_model points to models/movinet_a2 alongside other model files
    assert s.violence_model == "models/movinet_a2"
    assert s.violence_threshold == 0.65
    assert s.violence_gate_min_persons == 2
    assert s.alert_fsm_default_dedup_window_ms == 60_000
    assert s.alert_fsm_default_cooldown_ms == 60_000
    assert s.alert_fsm_default_sustain_ms == 500
    assert s.head_count_emit_interval_s == 1.0
    assert s.head_count_track_ttl_s == 30
    assert s.maintenance_cache_ttl_s == 30
    assert s.anomaly_max_consecutive_errors == 5
    assert s.alerts_stream_maxlen == 10_000
