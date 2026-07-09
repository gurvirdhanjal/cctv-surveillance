"""Application settings, loaded from environment variables prefixed VMS_."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for runtime configuration."""

    model_config = SettingsConfigDict(
        env_prefix="VMS_",
        case_sensitive=False,
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # connection strings — required
    db_url: str
    jwt_secret: str

    # connection strings — defaulted
    redis_url: str = "redis://localhost:6379/0"

    # model paths
    scrfd_model: str = "models/scrfd_10g_bnkps.onnx"
    adaface_model: str = "models/adaface_ir101_webface12m.onnx"
    bytetrack_config: str = "bytetrack_custom.yaml"
    botsort_config: str = "botsort_custom.yaml"
    # BoT-SORT lost-track retention (ghost tracklet bridge for short same-camera gaps).
    # Rendered into the tracker config at runtime — keep in sync with botsort_custom.yaml default.
    tracker_buffer_frames: int = 90
    # YOLO26m-pose replaces yolov8x-pose: equal accuracy (~69 mAP), 2x faster on TRT.
    # Accepts any Ultralytics-compatible path: .pt, .onnx, or .engine
    yolov8x_pose_model: str = "models/yolo26m-pose.pt"
    # TransReID ViT-B/16+ICS msmt17 — body Re-ID (768-dim, 384x128) — current production
    # Export: python scripts/export_transreid_onnx.py
    # Calibrated 2026-06-16 on webcam; re-calibrate on real footage before tightening thresholds.
    transreid_body_model: str = "models/transreid_body_msmt17.onnx"
    # PPE compliance — YOLOv8l SH17 ONNX (empty = disabled)
    # Export: from ultralytics import YOLO; YOLO('models/sh17_ppe_yolov8l.pt').export(format='onnx',imgsz=640,opset=11,simplify=True)
    ppe_model: str = ""
    ppe_helmet_threshold: float = 0.5
    ppe_vest_threshold: float = 0.5
    ppe_gloves_threshold: float = 0.5
    ppe_mask_threshold: float = 0.5
    ppe_gate_min_persons: int = 1
    ppe_conf_threshold: float = 0.25
    ppe_nms_iou_threshold: float = 0.45
    # SH17 class indices verified from notebook: helmet=10, vest=16, gloves=9, mask=5
    ppe_class_map_json: str = '{"helmet":10,"vest":16,"gloves":9,"mask":5}'

    # auth
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 8

    # inference thresholds (spec v1 §6 + v2 §C)
    scrfd_conf: float = 0.60
    # YOLO person-class detection threshold — separate from SCRFD face conf.
    # Raise to 0.60-0.70 for overhead factory views to suppress false positives on equipment.
    yolo_person_conf: float = 0.50
    adaface_min_sim: float = 0.72
    reid_cross_cam_sim: float = 0.65
    reid_margin: float = 0.08
    min_blur: float = 25.0
    min_face_px: int = 40
    # Skip body embedding / PPE for person crops narrower or shorter than this (px).
    # Crops this small carry no useful identity signal and waste GPU time.
    min_body_bbox_px: int = 64

    # identity
    reid_stale_ms: int = 300_000
    reid_gallery_size: int = 8
    reid_confirm_after_sightings: int = 3
    reid_confirmed_sim: float = 0.60  # face gallery threshold (confirmed tracks)
    reid_confirmed_stale_ms: int = 600_000
    reid_camera_topology_json: str = "{}"
    # Body Re-ID thresholds — TransReID ViT-B/16+ICS MSMT17 (768-dim, webcam-calibrated 2026-06-16)
    # Webcam calibration: 27 captures, 2 persons; same_p5=0.843, diff_p99=0.450, gap=0.393
    # Real-camera degradation estimated: same_p5~0.70-0.75, diff_p99~0.50-0.55
    # cross_cam > confirmed intentional: unconfirmed tracks (sparse gallery) are highest-risk merge.
    # Re-calibrate on real CAM105/CAM110 footage before tightening. Mandatory /advisor before change.
    reid_body_confirmed_sim: float = 0.65  # body gallery, confirmed tracks (8-slot gallery)
    reid_body_cross_cam_sim: float = (
        0.70  # body gallery, unconfirmed tracks (tighter — sparse gallery)
    )
    # ReID quality hardening (Phase 3) — all defaults conservative (no-op until calibrated)
    reid_quality_window_s: float = 2.0  # temporal window; keep best crop per window
    # Face and body quality floors are kept separate because the signals have different
    # units: face_quality = AdaFace pre-norm L2 (~10-32), body_quality = Laplacian
    # variance (~0-500+). Set independently after per-signal calibration on real footage.
    # Mandatory /advisor before raising either above 0.0.
    reid_face_quality_floor: float = 0.0  # AdaFace pre-norm L2 floor; 0.0 = accept all
    reid_body_quality_floor: float = 0.0  # Laplacian variance floor; 0.0 = accept all
    reid_enroll_dedup_sim: float = 0.95  # cosine sim ceiling for enrollment dedup
    # Pose-normalized torso crop for TransReID body Re-ID (Phase 3).
    # Extracts a shoulder+hip-bounded rect instead of the raw person bbox.
    torso_kp_conf_threshold: float = 0.3  # VMS_TORSO_KP_CONF_THRESHOLD
    torso_crop_pad_fraction: float = 0.20  # VMS_TORSO_CROP_PAD_FRACTION
    # Cross-camera Kalman floor-plane predictor (Phase 3 crosscam-accuracy).
    # Conservative defaults — spatial gate stays disabled until set per-pair in topology JSON.
    reid_predictor_history_len: int = 8  # floor positions retained per gid for the fit
    reid_predictor_max_predict_gap_ms: int = 900_000  # 15 min cap on extrapolation
    # Keypoint-gated face detection (YOLOv8x-pose)
    face_kpt_min_conf: float = 0.5  # nose + eye confidence to trigger SCRFD+AdaFace
    # BLE badge fallback
    ble_mqtt_broker: str = ""  # empty = BLE disabled
    ble_mqtt_port: int = 1883
    ble_mqtt_topic: str = "vms/ble/events"
    ble_stream_maxlen: int = 10_000
    ble_zone_reader_map_json: str = "{}"  # {"reader_mac": zone_id, ...}
    zone_cache_ttl_s: int = 30

    # pipeline tuning
    stale_threshold_ms: int = 200
    db_flush_rows: int = 100
    db_flush_ms: int = 500
    redis_stream_maxlen: int = 500
    redis_stream_retry_attempts: int = 3
    redis_stream_retry_delay_ms: int = 100
    rtsp_failure_threshold: int = 5
    rtsp_backoff_delays_ms: tuple[int, ...] = (1000, 2000, 4000, 8000, 16000, 32000)

    # violence detection — R(2+1)D-18 (torchvision, no TensorFlow required)
    # Points to a .pt state-dict file OR any other value triggers auto-download (~130 MB).
    # Legacy MoViNet SavedModel directory paths are detected and auto-upgraded.
    # Set empty to disable. Pre-cache: python -c "from torchvision.models.video import
    #   R2Plus1D_18_Weights,r2plus1d_18; import torch;
    #   torch.save(r2plus1d_18(weights=R2Plus1D_18_Weights.KINETICS400_V1).state_dict(),
    #   'models/r2plus1d_18_violence.pt')"
    violence_model: str = "models/movinet_a2"
    violence_threshold: float = 0.65  # sigmoid score threshold [0, 1]
    violence_gate_min_persons: int = 2  # only run when >= N persons detected
    violence_clip_frames: int = 16  # frames per clip (buffer depth)
    violence_clip_stride: int = 8  # run inference every N frames (lower = more CPU)

    # alert FSM
    alert_fsm_default_dedup_window_ms: int = 60_000
    alert_fsm_default_cooldown_ms: int = 60_000
    alert_fsm_default_sustain_ms: int = 500

    # head count
    head_count_emit_interval_s: float = 1.0
    head_count_track_ttl_s: int = 30
    # EMA smoothing for the API snapshot (0 = raw counts, 1 = no update).
    # 0.3 damps RTSP flicker while tracking real changes in ~5 frames.
    head_count_ema_alpha: float = 0.3

    # maintenance
    maintenance_cache_ttl_s: int = 30
    maintenance_calendar_max_range_days: int = 90

    # camera profiler
    profiler_probe_duration_s: int = 60
    profiler_sample_frames: int = 30
    profiler_shutter_skew_threshold: float = 0.04
    profiler_focus_full_min: float = 30.0
    profiler_focus_mid_min: float = 15.0
    profiler_fps_full_min: float = 12.0
    profiler_fps_mid_min: float = 8.0
    profiler_res_full_min_h: int = 1080
    profiler_res_mid_min_h: int = 720
    profiler_rtsp_open_timeout_ms: int = 5000
    profiler_rtsp_read_timeout_ms: int = 5000

    # anomaly orchestrator
    anomaly_max_consecutive_errors: int = 5
    alerts_stream_maxlen: int = 10_000
    dead_alerts_stream_maxlen: int = 1_000

    # dispatcher retry tuning
    alert_dispatcher_retry_delays_s: tuple[int, ...] = (1, 4, 16)
    alert_dispatcher_max_attempts: int = 3

    # dispatcher — channel credentials (empty = channel disabled)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_from: str = ""
    smtp_user: str = ""
    smtp_password: str = ""
    slack_bot_token: str = ""
    telegram_bot_token: str = ""
    webhook_secret: str = ""

    # forensic clip search
    forensic_window_default_s: int = Field(default=30, ge=1)
    forensic_window_min_s: int = Field(default=5, ge=1)
    forensic_window_max_s: int = Field(default=3600, ge=1)

    # audit export
    audit_export_max_rows: int = Field(default=100_000, ge=1)

    # person timeline (phase 4P task 1b, model-stack spec §9.2)
    # events on the same (camera, track) closer than this coalesce into one visit span
    timeline_gap_s: float = Field(default=10.0, gt=0.0)
    timeline_max_spans: int = Field(default=500, ge=1)

    # analytics rollups + caching (phase 4P tasks 3-4)
    rollup_backfill_max_hours: int = Field(default=48, ge=1)
    analytics_cache_ttl_s: int = Field(default=60, ge=1)

    # phase 6 — gpu acceleration (§5 of 2026-06-13-vms-gpu-acceleration.md)
    # master switch; False = current CUDA/CPU path (no change to existing deployments)
    gpu_tensorrt_enabled: bool = False
    gpu_tensorrt_fp16: bool = True  # arch-gated at runtime; RTX 2000 Ada supports FP16
    # INT8 detectors only — NEVER embedders without /advisor sign-off (spec §6.2 hard rule)
    gpu_tensorrt_int8: bool = False
    gpu_tensorrt_engine_cache_dir: str = "models/trt_engines"
    gpu_tensorrt_workspace_mb: int = 4096
    gpu_onnx_export_dir: str = "models/onnx_exported"
    # Representative frames dir for INT8 PTQ calibration (§6.2); empty = disabled
    gpu_int8_calibration_dir: str = ""
    # NVDEC hardware decode — moves RTSP H.264 decode from CPU to GPU video engine (§6.3)
    gpu_nvdec_enabled: bool = False
    # Triton Inference Server URL (§6.4); empty = in-process ORT EP (default)
    gpu_triton_url: str = ""
    # 1 = detect every frame (current behaviour). N>1 = YOLO runs every N frames,
    # BoT-SORT coasts between runs. Cascade stages (SCRFD, AdaFace) are exempt.
    detector_interval_frames: int = 1
    # Adaptive detector interval (§6.0.3) — self-adjusts interval per camera based on activity
    detector_interval_adaptive: bool = False
    detector_interval_max: int = 4  # ceiling for adaptive interval and per-camera override cap
    detector_adapt_window: int = (
        5  # consecutive no-new-detection YOLO frames before raising interval
    )
    # Motion gate pre-filter (§6.0.25) — skip YOLO entirely on quiescent frames
    motion_gate_enabled: bool = False
    motion_gate_method: str = "frame_diff"  # "frame_diff" | "mog2"
    motion_gate_min_pixel_diff_pct: float = (
        0.5  # fraction of pixels that must change before YOLO fires
    )
    motion_gate_roi_crop_enabled: bool = False  # crop YOLO input to motion-region bbox + margin
    motion_gate_roi_margin_px: int = 32  # expand motion ROI by this many pixels before crop

    # frontend / real-time
    # Comma-separated list of allowed CORS origins for the Socket.io server.
    # Set to the React dev server in development, production origin in production.
    # Empty string or "*" allows all origins (dev default).
    frontend_origin: str = "*"
    # When True, FastAPI mounts frontend/dist/ as a SPA (catch-all returns index.html).
    # Default off in dev (Vite dev server handles frontend). Enable in production with
    # VMS_SERVE_FRONTEND=true after running `pnpm build` inside frontend/.
    serve_frontend: bool = False

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
