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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    return Settings()  # type: ignore[call-arg]
