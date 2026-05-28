"""Application settings, loaded from environment variables prefixed VMS_."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="VMS_",
        case_sensitive=False,
        extra="ignore",
    )

    # connection strings — required
    db_url: str
    jwt_secret: str

    # connection strings — defaulted
    redis_url: str = "redis://localhost:6379/0"

    # model paths
    scrfd_model: str = "models/scrfd_2.5g.onnx"
    adaface_model: str = "models/adaface_ir50.onnx"
    bytetrack_config: str = "bytetrack_custom.yaml"

    # auth
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 8

    # inference thresholds (spec v1 §6 + v2 §C)
    scrfd_conf: float = 0.60
    adaface_min_sim: float = 0.72
    reid_cross_cam_sim: float = 0.65
    reid_margin: float = 0.08
    min_blur: float = 25.0
    min_face_px: int = 40

    # identity
    reid_stale_ms: int = 300_000
    zone_cache_ttl_s: int = 30

    # pipeline tuning
    stale_threshold_ms: int = 200
    db_flush_rows: int = 100
    db_flush_ms: int = 500
    redis_stream_maxlen: int = 500
    rtsp_failure_threshold: int = 5
    rtsp_backoff_delays_ms: tuple[int, ...] = (1000, 2000, 4000, 8000, 16000, 32000)

    # violence detection — MoViNet A2 Stream (TF SavedModel via kagglehub or tar.gz)
    # Set to the SavedModel directory path.
    # Download: python scripts/download_movinet_a2.py
    #   OR: curl -L -o ~/Downloads/model.tar.gz \
    #     https://www.kaggle.com/api/v1/models/google/movinet/tensorFlow2/a2-stream-kinetics-600-classification/2/download
    #   Then: tar xf ~/Downloads/model.tar.gz -C models/movinet_a2/
    #   Then set: VMS_VIOLENCE_MODEL=models/movinet_a2
    violence_model: str = ""  # empty = disabled until downloaded
    violence_threshold: float = 0.65  # sigmoid score threshold [0, 1]
    violence_gate_min_persons: int = 2  # only run when >= N persons detected

    # alert FSM
    alert_fsm_default_dedup_window_ms: int = 60_000
    alert_fsm_default_cooldown_ms: int = 60_000
    alert_fsm_default_sustain_ms: int = 500

    # head count
    head_count_emit_interval_s: float = 1.0
    head_count_track_ttl_s: int = 30

    # maintenance
    maintenance_cache_ttl_s: int = 30

    # anomaly orchestrator
    anomaly_max_consecutive_errors: int = 5
    alerts_stream_maxlen: int = 10_000

    # storage backend
    storage_backend: str = "local"  # "local" | "minio"
    storage_local_dir: str = "thumbnails"  # base dir for LocalStorageBackend
    minio_endpoint: str = ""  # e.g. "http://minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "vms-media"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()  # type: ignore[call-arg]
