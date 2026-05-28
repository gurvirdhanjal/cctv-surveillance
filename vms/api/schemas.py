"""Pydantic request/response schemas for the VMS API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PersonCreate(BaseModel):
    name: str = Field(..., max_length=200)
    employee_id: str = Field(..., max_length=50)


class PersonResponse(BaseModel):
    person_id: int
    name: str
    employee_id: str
    is_active: bool

    model_config = {"from_attributes": True}


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


class AlertResponse(BaseModel):
    alert_id: int
    alert_type: str
    severity: str
    state: str
    camera_id: int
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


class SnapshotResponse(BaseModel):
    ts: str
    schema_version: str = "1"
    head_count: dict[str, Any]
    active_alerts: list[AlertResponse]
    cameras: list[dict[str, Any]]
    degraded: dict[str, Any] | None = None
