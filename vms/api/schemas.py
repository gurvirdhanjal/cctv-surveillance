"""Pydantic request/response schemas for the VMS API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from croniter import croniter  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PersonCreate(BaseModel):
    name: str = Field(..., max_length=200)
    employee_id: str = Field(..., max_length=50)


class PersonResponse(BaseModel):
    person_id: int
    name: str
    employee_id: str
    is_active: bool

    model_config = {"from_attributes": True}


class PersonListResponse(BaseModel):
    items: list[PersonResponse]
    total: int
    limit: int
    offset: int


class EmbeddingCreate(BaseModel):
    embedding: list[float] = Field(..., min_length=512, max_length=512)
    quality_score: float = Field(..., ge=0.0, le=1.0)


class EmbeddingResponse(BaseModel):
    embedding_id: int
    person_id: int
    quality_score: float

    model_config = {"from_attributes": True}


class PurgeRequest(BaseModel):
    confirmation_name: str = Field(..., description="Must match person.name exactly")
    reason: str = Field(..., min_length=10, max_length=500)


class TokenRequest(BaseModel):
    username: str = Field(..., max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class HealthResponse(BaseModel):
    status: str
    version: str


class ReadinessResponse(BaseModel):
    db: str
    redis: str


class AlertResponse(BaseModel):
    alert_id: int
    alert_type: str
    severity: str
    state: str
    # camera_id is None for SYSTEM_CRITICAL alerts
    camera_id: int | None
    zone_id: int | None
    person_id: int | None
    triggered_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    suppressed_by_window_id: int | None
    dedup_key: str | None

    model_config = {"from_attributes": True}


class AnomalyDetectorResponse(BaseModel):
    detector_id: int
    alert_type: str
    class_path: str
    is_enabled: bool
    config_json: str | None
    model_version: str | None

    model_config = {"from_attributes": True}


class AnomalyDetectorUpdate(BaseModel):
    is_enabled: bool | None = None
    config_json: dict[str, Any] | None = None


class MaintenanceWindowResponse(BaseModel):
    window_id: int
    name: str
    scope_type: str
    scope_id: int
    schedule_type: str
    starts_at: datetime | None
    ends_at: datetime | None
    cron_expr: str | None
    duration_minutes: int | None
    suppress_alert_types: str | None
    is_active: bool
    reason: str | None

    model_config = {"from_attributes": True}


_MW_VALID_SCOPES = frozenset({"CAMERA", "ZONE"})
_MW_VALID_SCHEDULES = frozenset({"ONE_TIME", "RECURRING"})


def validate_window_coherence(
    *,
    schedule_type: str,
    starts_at: datetime | None,
    ends_at: datetime | None,
    cron_expr: str | None,
    duration_minutes: int | None,
) -> None:
    """Mirror the DB CHECK constraints (chk_mw_one_time/recurring/window_positive).

    Raises ValueError on violation so callers can surface a 422. Used by both the
    POST create schema and the PATCH route (on merged existing+patch state).
    """
    if schedule_type == "ONE_TIME":
        if starts_at is None or ends_at is None:
            raise ValueError("ONE_TIME windows require starts_at and ends_at")
        if ends_at <= starts_at:
            raise ValueError("ends_at must be after starts_at")
    elif schedule_type == "RECURRING":
        if cron_expr is None or duration_minutes is None:
            raise ValueError("RECURRING windows require cron_expr and duration_minutes")
        if duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")
        if not croniter.is_valid(cron_expr):
            raise ValueError(f"invalid cron expression: {cron_expr!r}")


class MaintenanceWindowCreate(BaseModel):
    name: str = Field(..., max_length=200)
    scope_type: str
    scope_id: int
    schedule_type: str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    cron_expr: str | None = Field(default=None, max_length=100)
    duration_minutes: int | None = None
    suppress_alert_types: list[str] | None = None
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("scope_type")
    @classmethod
    def _validate_scope(cls, v: str) -> str:
        if v not in _MW_VALID_SCOPES:
            raise ValueError(f"scope_type must be one of {sorted(_MW_VALID_SCOPES)}")
        return v

    @field_validator("schedule_type")
    @classmethod
    def _validate_schedule(cls, v: str) -> str:
        if v not in _MW_VALID_SCHEDULES:
            raise ValueError(f"schedule_type must be one of {sorted(_MW_VALID_SCHEDULES)}")
        return v

    @model_validator(mode="after")
    def _validate_coherence(self) -> MaintenanceWindowCreate:
        validate_window_coherence(
            schedule_type=self.schedule_type,
            starts_at=self.starts_at,
            ends_at=self.ends_at,
            cron_expr=self.cron_expr,
            duration_minutes=self.duration_minutes,
        )
        return self


class MaintenanceWindowUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    scope_type: str | None = None
    scope_id: int | None = None
    schedule_type: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    cron_expr: str | None = Field(default=None, max_length=100)
    duration_minutes: int | None = None
    suppress_alert_types: list[str] | None = None
    reason: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None

    @field_validator("scope_type")
    @classmethod
    def _validate_scope(cls, v: str | None) -> str | None:
        if v is not None and v not in _MW_VALID_SCOPES:
            raise ValueError(f"scope_type must be one of {sorted(_MW_VALID_SCOPES)}")
        return v

    @field_validator("schedule_type")
    @classmethod
    def _validate_schedule(cls, v: str | None) -> str | None:
        if v is not None and v not in _MW_VALID_SCHEDULES:
            raise ValueError(f"schedule_type must be one of {sorted(_MW_VALID_SCHEDULES)}")
        return v


class MaintenanceWindowPatchResponse(MaintenanceWindowResponse):
    warning: str | None = None


class CalendarSlot(BaseModel):
    window_id: int
    name: str
    scope_type: str
    scope_id: int
    starts_at: datetime
    ends_at: datetime
    is_recurring: bool
    suppress_alert_types: list[str] | None


class CalendarResponse(BaseModel):
    slots: list[CalendarSlot]
    from_: datetime = Field(..., alias="from")
    to: datetime
    total_slots: int

    model_config = ConfigDict(populate_by_name=True)


class SnapshotResponse(BaseModel):
    ts: str
    schema_version: str = "1"
    head_count: dict[str, Any]
    active_alerts: list[AlertResponse]
    cameras: list[dict[str, Any]]
    degraded: dict[str, Any] | None = None


# ── Camera schemas ──────────────────────────────────────────────────────────

VALID_TIERS = frozenset({"FULL", "MID", "LOW"})
VALID_SHUTTER_TYPES = frozenset({"rolling", "global", "unknown"})


class CameraCreate(BaseModel):
    name: str = Field(..., max_length=200)
    rtsp_url: str = Field(..., max_length=500)
    capability_tier: str = Field("FULL")
    shutter_type: str = Field("unknown")
    worker_group: int | None = None

    @field_validator("capability_tier")
    @classmethod
    def validate_tier(cls, v: str) -> str:
        if v not in VALID_TIERS:
            raise ValueError(f"capability_tier must be one of {sorted(VALID_TIERS)}")
        return v

    @field_validator("shutter_type")
    @classmethod
    def validate_shutter(cls, v: str) -> str:
        if v not in VALID_SHUTTER_TYPES:
            raise ValueError(f"shutter_type must be one of {sorted(VALID_SHUTTER_TYPES)}")
        return v


class CameraUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    rtsp_url: str | None = Field(None, max_length=500)
    is_active: bool | None = None
    capability_tier: str | None = None
    shutter_type: str | None = None
    worker_group: int | None = None

    @field_validator("capability_tier")
    @classmethod
    def validate_tier(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TIERS:
            raise ValueError(f"capability_tier must be one of {sorted(VALID_TIERS)}")
        return v

    @field_validator("shutter_type")
    @classmethod
    def validate_shutter(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_SHUTTER_TYPES:
            raise ValueError(f"shutter_type must be one of {sorted(VALID_SHUTTER_TYPES)}")
        return v


class CameraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    camera_id: int
    name: str
    rtsp_url: str
    is_active: bool
    capability_tier: str
    shutter_type: str
    profile_data: str | None
    profiled_at: datetime | None
    model_overrides: str | None
    worker_group: int | None
    recalibrate_required_at: datetime | None = None


class CameraHardwareUpdate(BaseModel):
    shutter_type: str = Field(..., pattern="^(rolling|global|unknown)$")
    capability_tier: str | None = Field(default=None, pattern="^(FULL|MID|LOW)$")


class CameraOverridesUpdate(BaseModel):
    models: dict[str, Any] | None = None
    thresholds: dict[str, Any] | None = None


class ResolvedSettingItem(BaseModel):
    value: Any
    source: str


class ResolvedConfigResponse(BaseModel):
    camera_id: int
    settings: dict[str, ResolvedSettingItem]


class ProfileData(BaseModel):
    resolution_w: int | None = None
    resolution_h: int | None = None
    fps_measured: float | None = None
    focus_score: float | None = None
    frame_drop_rate: float | None = None
    brightness_mean: float | None = None
    is_analog_via_encoder: bool | None = None
    tier_reason: str | None = None
    codec: str | None = None
    shutter_suggestion: str | None = Field(default=None, pattern="^(rolling|global|unknown)$")
    shutter_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    suggested_tier: str | None = Field(default=None, pattern="^(FULL|MID|LOW)$")


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    camera_id: int
    profile_data: ProfileData | None
    profiled_at: datetime | None
    capability_tier: str
    shutter_type: str
    tier_reason: str | None = None


# ── Alert Routing ──────────────────────────────────────────────────────────

_VALID_CHANNELS = frozenset({"EMAIL", "SLACK", "TELEGRAM", "WEBHOOK", "WEBSOCKET"})


class AlertRoutingCreate(BaseModel):
    alert_type: str | None = None
    severity: str | None = None
    zone_id: int | None = None
    channel: str
    target: str

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        if v not in _VALID_CHANNELS:
            raise ValueError(f"channel must be one of {sorted(_VALID_CHANNELS)}")
        return v


class AlertRoutingUpdate(BaseModel):
    alert_type: str | None = None
    severity: str | None = None
    zone_id: int | None = None
    channel: str | None = None
    target: str | None = None
    is_active: bool | None = None

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str | None) -> str | None:
        if v is not None and v not in _VALID_CHANNELS:
            raise ValueError(f"channel must be one of {sorted(_VALID_CHANNELS)}")
        return v


class AlertRoutingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    routing_id: int
    alert_type: str | None
    severity: str | None
    zone_id: int | None
    channel: str
    target: str
    is_active: bool


# ── Audit schemas ────────────────────────────────────────────────────────────


class AuditVerifyResponse(BaseModel):
    rows_checked: int
    broken_chain_at: datetime | None


# ── Forensic schemas ──────────────────────────────────────────────────────────


class ForensicClipItem(BaseModel):
    clip_emb_id: int
    global_track_id: str
    camera_id: int
    event_ts: datetime
    snapshot_url: str


class ForensicClipsResponse(BaseModel):
    clips: list[ForensicClipItem]
    total: int


class ZoneCreate(BaseModel):
    name: str = Field(..., max_length=200)
    polygon: list[tuple[float, float]] = Field(..., min_length=3)
    allowed_hours: str | None = None
    max_capacity: int | None = Field(default=None, ge=0)
    loiter_threshold_s: int = Field(default=180, ge=0)
    floor_plan_id: int | None = None


class ZoneUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    polygon: list[tuple[float, float]] | None = Field(default=None, min_length=3)
    allowed_hours: str | None = None
    max_capacity: int | None = Field(default=None, ge=0)
    loiter_threshold_s: int | None = Field(default=None, ge=0)
    floor_plan_id: int | None = None
    is_active: bool | None = None


class ZoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=False)
    zone_id: int
    name: str
    polygon: list[tuple[float, float]] | None
    allowed_hours: str | None
    max_capacity: int | None
    loiter_threshold_s: int
    floor_plan_id: int | None
    is_active: bool
