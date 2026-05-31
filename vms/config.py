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
    botsort_config: str = "botsort_custom.yaml"
    yolov8x_pose_model: str = "models/yolov8x-pose.pt"
    # OSNet AIN x1.0 msmt17 — body Re-ID, angle-invariant
    # Download: python scripts/download_osnet_ain_msmt17.py
    osnet_ain_model: str = "models/osnet_ain_x1_0_msmt17.pth"

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
    reid_gallery_size: int = 8
    reid_confirm_after_sightings: int = 3
    reid_confirmed_sim: float = 0.60        # face gallery threshold (confirmed tracks)
    reid_confirmed_stale_ms: int = 600_000
    reid_camera_topology_json: str = "{}"
    # Body Re-ID thresholds — calibrated on DukeMTMC-reID with OSNet AIN x1.0 msmt17
    # Simulation: Rank-1=73%, mAP=58.8%, same-person p5=0.511, diff-person p99=0.713
    # Conservative (95% recall): confirmed=0.51, cross-cam=0.56
    # Balanced   (99% FP guard): confirmed=0.69, cross-cam=0.74
    # See scripts/simulate_osnet_reid.py to re-calibrate on your camera setup.
    reid_body_confirmed_sim: float = 0.51   # body gallery, confirmed tracks (95% recall)
    reid_body_cross_cam_sim: float = 0.56   # body gallery, unconfirmed tracks
    # Keypoint-gated face detection (YOLOv8x-pose)
    face_kpt_min_conf: float = 0.5   # nose + eye confidence to trigger SCRFD+AdaFace
    # BLE badge fallback
    ble_mqtt_broker: str = ""          # empty = BLE disabled
    ble_mqtt_port: int = 1883
    ble_mqtt_topic: str = "vms/ble/events"
    ble_stream_maxlen: int = 10_000
    ble_zone_reader_map_json: str = "{}"   # {"reader_mac": zone_id, ...}
    zone_cache_ttl_s: int = 30

    # pipeline tuning
    stale_threshold_ms: int = 200
    db_flush_rows: int = 100
    db_flush_ms: int = 500
    redis_stream_maxlen: int = 500
    rtsp_failure_threshold: int = 5
    rtsp_backoff_delays_ms: tuple[int, ...] = (1000, 2000, 4000, 8000, 16000, 32000)

    # violence detection — MoViNet A2 Stream (TF SavedModel)
    # Points to models/movinet_a2/ alongside scrfd/adaface/yolo.
    # Run once to install: python scripts/download_movinet_a2.py
    # Model is gitignored (large binary) — works after download with no extra config.
    violence_model: str = "models/movinet_a2"
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
