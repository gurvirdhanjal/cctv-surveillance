"""ORM models for all VMS v2 database tables."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vms.db.session import Base

# ─────────────────────────────────────────────────────────────────────
# Topology
# ─────────────────────────────────────────────────────────────────────


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        CheckConstraint("capability_tier IN ('FULL', 'MID', 'LOW')", name="chk_camera_tier"),
    )

    camera_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rtsp_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    capability_tier: Mapped[str] = mapped_column(String(10), nullable=False, default="FULL")
    profile_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    profiled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    model_overrides: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_group: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Zone(Base):
    __tablename__ = "zones"

    zone_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allowed_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    loiter_threshold_s: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    polygon_json: Mapped[str | None] = mapped_column(Text, nullable=True)


# ─────────────────────────────────────────────────────────────────────
# Users and permissions
# ─────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('guard', 'manager', 'admin')", name="chk_user_role"),
    )

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="guard")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UserCameraPermission(Base):
    __tablename__ = "user_camera_permissions"
    __table_args__ = (UniqueConstraint("user_id", "camera_id", name="uq_user_camera"),)

    perm_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.camera_id", ondelete="CASCADE"), nullable=False
    )


# ─────────────────────────────────────────────────────────────────────
# Persons and embeddings
# ─────────────────────────────────────────────────────────────────────


class Person(Base):
    __tablename__ = "persons"

    person_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    employee_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    embeddings: Mapped[list[PersonEmbedding]] = relationship(
        "PersonEmbedding", back_populates="person", cascade="all, delete-orphan"
    )


class PersonEmbedding(Base):
    __tablename__ = "person_embeddings"
    __table_args__ = (
        CheckConstraint(
            "quality_score >= 0.0 AND quality_score <= 1.0",
            name="chk_embedding_quality",
        ),
        Index("ix_person_embeddings_person_id", "person_id"),
    )

    embedding_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.person_id", ondelete="CASCADE"), nullable=False
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(512), nullable=False)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    person: Mapped[Person] = relationship("Person", back_populates="embeddings")


# ─────────────────────────────────────────────────────────────────────
# Maintenance windows (declared before Alert due to FK)
# ─────────────────────────────────────────────────────────────────────


class MaintenanceWindow(Base):
    __tablename__ = "maintenance_windows"
    __table_args__ = (
        CheckConstraint("scope_type IN ('CAMERA', 'ZONE')", name="chk_mw_scope"),
        CheckConstraint("schedule_type IN ('ONE_TIME', 'RECURRING')", name="chk_mw_sched"),
        CheckConstraint(
            "schedule_type <> 'ONE_TIME' OR (starts_at IS NOT NULL AND ends_at IS NOT NULL)",
            name="chk_mw_one_time",
        ),
        CheckConstraint(
            "schedule_type <> 'RECURRING' OR (cron_expr IS NOT NULL AND duration_minutes IS NOT NULL)",
            name="chk_mw_recurring",
        ),
        CheckConstraint(
            "(schedule_type <> 'ONE_TIME' OR ends_at > starts_at)"
            " AND (schedule_type <> 'RECURRING' OR duration_minutes > 0)",
            name="chk_mw_window_positive",
        ),
        Index("idx_mw_active_scope", "scope_type", "scope_id"),
    )

    window_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[int] = mapped_column(Integer, nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cron_expr: Mapped[str | None] = mapped_column(String(100), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suppress_alert_types: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[int] = mapped_column(
        # NO ACTION: must not delete user with active windows
        ForeignKey("users.user_id", ondelete="NO ACTION"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────
# Alerts
# ─────────────────────────────────────────────────────────────────────


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "(acknowledged_at IS NULL OR acknowledged_at >= triggered_at)"
            " AND (resolved_at IS NULL OR resolved_at >= triggered_at)"
            " AND (resolved_at IS NULL OR acknowledged_at IS NULL"
            "      OR resolved_at >= acknowledged_at)",
            name="chk_alert_resolution_order",
        ),
        Index("ix_alerts_alert_type", "alert_type"),
        Index("ix_alerts_triggered_at", "triggered_at"),
    )

    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.camera_id", ondelete="NO ACTION"), nullable=False
    )
    # zone_id and person_id intentionally not FK'd: zones reshape; persons are purged
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    global_track_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    person_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    suppressed_by_window_id: Mapped[int | None] = mapped_column(
        ForeignKey("maintenance_windows.window_id", ondelete="SET NULL"), nullable=True
    )

    dispatches: Mapped[list[AlertDispatch]] = relationship(
        "AlertDispatch", back_populates="alert", cascade="all, delete-orphan"
    )


class AlertRouting(Base):
    __tablename__ = "alert_routing"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('EMAIL', 'SLACK', 'TELEGRAM', 'WEBHOOK', 'WEBSOCKET')",
            name="chk_routing_channel",
        ),
    )

    routing_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(10), nullable=True)
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AlertDispatch(Base):
    __tablename__ = "alert_dispatches"
    __table_args__ = (Index("idx_dispatches_alert", "alert_id"),)

    dispatch_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.alert_id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    attempt_n: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dispatched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    alert: Mapped[Alert] = relationship("Alert", back_populates="dispatches")


# ─────────────────────────────────────────────────────────────────────
# Tracking
# ─────────────────────────────────────────────────────────────────────


class TrackingEvent(Base):
    __tablename__ = "tracking_events"
    __table_args__ = (
        CheckConstraint("bbox_x2 > bbox_x1 AND bbox_y2 > bbox_y1", name="chk_bbox_valid"),
        UniqueConstraint("camera_id", "local_track_id", "event_ts", name="uq_tracking_idem"),
        Index("ix_tracking_events_global_track_id", "global_track_id"),
        Index("ix_tracking_events_person_id", "person_id"),
        Index("ix_tracking_events_camera_id", "camera_id"),
        Index("ix_tracking_events_event_ts", "event_ts"),
    )

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.camera_id", ondelete="NO ACTION"), nullable=False
    )
    local_track_id: Mapped[str] = mapped_column(String(50), nullable=False)
    global_track_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # FK is intentionally nullable: person_id set to NULL on GDPR purge
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.person_id", ondelete="SET NULL"), nullable=True
    )
    # zone_id intentionally not FK'd: zones can reshape or be retired
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ingest_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    bbox_x1: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_y1: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_x2: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox_y2: Mapped[int] = mapped_column(Integer, nullable=False)
    floor_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    floor_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    seq_id: Mapped[int] = mapped_column(BigInteger, nullable=False)


class ReidMatch(Base):
    __tablename__ = "reid_matches"
    __table_args__ = (
        Index("ix_reid_global_track_1", "global_track_id_1"),
        Index("ix_reid_global_track_2", "global_track_id_2"),
        Index("ix_reid_person", "person_id"),
    )

    reid_match_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    global_track_id_1: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    global_track_id_2: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.person_id", ondelete="SET NULL"), nullable=True
    )
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    event_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ZonePresence(Base):
    __tablename__ = "zone_presence"
    __table_args__ = (
        CheckConstraint(
            "exited_at IS NULL OR exited_at >= entered_at",
            name="chk_presence_temporal",
        ),
        UniqueConstraint("zone_id", "global_track_id", "entered_at", name="uq_zone_presence"),
        Index("ix_zp_zone_id", "zone_id"),
        Index("ix_zp_global_track", "global_track_id"),
    )

    presence_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    zone_id: Mapped[int] = mapped_column(
        ForeignKey("zones.zone_id", ondelete="NO ACTION"), nullable=False
    )
    global_track_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    entered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    exited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# ─────────────────────────────────────────────────────────────────────
# Anomaly detectors registry
# ─────────────────────────────────────────────────────────────────────


class AnomalyDetector(Base):
    __tablename__ = "anomaly_detectors"

    detector_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    class_path: Mapped[str] = mapped_column(String(200), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────
# Forensic CLIP embeddings
# ─────────────────────────────────────────────────────────────────────


class PersonClipEmbedding(Base):
    __tablename__ = "person_clip_embeddings"
    __table_args__ = (
        UniqueConstraint("global_track_id", "event_ts", name="uq_clip_track_ts"),
        Index("ix_clip_ts", "event_ts"),
        Index("ix_clip_global_track", "global_track_id"),
    )

    clip_emb_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    global_track_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    camera_id: Mapped[int] = mapped_column(
        ForeignKey("cameras.camera_id", ondelete="NO ACTION"), nullable=False
    )
    event_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(512), nullable=False)
    snapshot_path: Mapped[str] = mapped_column(String(500), nullable=False)


# ─────────────────────────────────────────────────────────────────────
# Model registry (manifest DB projection)
# ─────────────────────────────────────────────────────────────────────


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    model_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    fine_tunable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────────────
# Audit log (immutable; written only via vms.db.audit.write_audit_event)
# ─────────────────────────────────────────────────────────────────────


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_ts", "event_ts"),
        Index("idx_audit_target", "target_type", "target_id"),
    )

    audit_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
