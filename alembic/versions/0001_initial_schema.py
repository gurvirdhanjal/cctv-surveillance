"""Initial VMS v2 schema — all tables, indexes, constraints, pgvector types.

Revision ID: 0001
Revises:
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    # ── pgvector extension (PostgreSQL only) ───────────────────────────
    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pgvector")

    # ── cameras ───────────────────────────────────────────────────────
    op.create_table(
        "cameras",
        sa.Column("camera_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("rtsp_url", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("capability_tier", sa.String(10), nullable=False, server_default="FULL"),
        sa.Column("profile_data", sa.Text(), nullable=True),
        sa.Column("profiled_at", sa.DateTime(), nullable=True),
        sa.Column("model_overrides", sa.Text(), nullable=True),
        sa.Column("worker_group", sa.Integer(), nullable=True),
        sa.CheckConstraint("capability_tier IN ('FULL', 'MID', 'LOW')", name="chk_camera_tier"),
    )

    # ── zones ─────────────────────────────────────────────────────────
    op.create_table(
        "zones",
        sa.Column("zone_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_restricted", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("max_capacity", sa.Integer(), nullable=True),
        sa.Column("allowed_hours", sa.Text(), nullable=True),
        sa.Column("loiter_threshold_s", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("polygon_json", sa.Text(), nullable=True),
    )

    # ── users ─────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("user_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="guard"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.CheckConstraint("role IN ('guard', 'manager', 'admin')", name="chk_user_role"),
    )

    # ── user_camera_permissions ────────────────────────────────────────
    op.create_table(
        "user_camera_permissions",
        sa.Column("perm_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "camera_id",
            sa.Integer(),
            sa.ForeignKey("cameras.camera_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "camera_id", name="uq_user_camera"),
    )

    # ── persons ────────────────────────────────────────────────────────
    op.create_table(
        "persons",
        sa.Column("person_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("employee_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("thumbnail_path", sa.String(500), nullable=True),
        sa.Column("purged_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text(
                "now()" if op.get_bind().dialect.name == "postgresql" else "CURRENT_TIMESTAMP"
            ),
        ),
        sa.UniqueConstraint("employee_id", name="uq_persons_employee_id"),
    )

    # ── person_embeddings ──────────────────────────────────────────────
    # embedding: vector(512) on PostgreSQL, BLOB on SQLite
    if dialect == "postgresql":
        op.create_table(
            "person_embeddings",
            sa.Column("embedding_id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "person_id",
                sa.Integer(),
                sa.ForeignKey("persons.person_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("embedding", sa.Text(), nullable=False),  # overridden below
            sa.Column("quality_score", sa.Float(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.CheckConstraint(
                "quality_score >= 0.0 AND quality_score <= 1.0",
                name="chk_embedding_quality",
            ),
        )
        op.execute(
            "ALTER TABLE person_embeddings ALTER COLUMN embedding TYPE vector(512) USING embedding::vector(512)"
        )
    else:
        op.create_table(
            "person_embeddings",
            sa.Column("embedding_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "person_id",
                sa.Integer(),
                sa.ForeignKey("persons.person_id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("embedding", sa.LargeBinary(), nullable=False),
            sa.Column("quality_score", sa.Float(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.CheckConstraint(
                "quality_score >= 0.0 AND quality_score <= 1.0",
                name="chk_embedding_quality",
            ),
        )
    op.create_index("ix_person_embeddings_person_id", "person_embeddings", ["person_id"])
    if dialect == "postgresql":
        op.execute(
            "CREATE INDEX ix_person_embeddings_hnsw ON person_embeddings "
            "USING hnsw (embedding vector_cosine_ops)"
        )

    # ── maintenance_windows ────────────────────────────────────────────
    op.create_table(
        "maintenance_windows",
        sa.Column("window_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("scope_type", sa.String(20), nullable=False),
        sa.Column("scope_id", sa.Integer(), nullable=False),
        sa.Column("schedule_type", sa.String(20), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("cron_expr", sa.String(100), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("suppress_alert_types", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.user_id", ondelete="NO ACTION"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()" if dialect == "postgresql" else "CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("scope_type IN ('CAMERA', 'ZONE')", name="chk_mw_scope"),
        sa.CheckConstraint("schedule_type IN ('ONE_TIME', 'RECURRING')", name="chk_mw_sched"),
        sa.CheckConstraint(
            "schedule_type <> 'ONE_TIME' OR (starts_at IS NOT NULL AND ends_at IS NOT NULL)",
            name="chk_mw_one_time",
        ),
        sa.CheckConstraint(
            "schedule_type <> 'RECURRING' OR (cron_expr IS NOT NULL AND duration_minutes IS NOT NULL)",
            name="chk_mw_recurring",
        ),
        sa.CheckConstraint(
            "(schedule_type <> 'ONE_TIME' OR ends_at > starts_at)"
            " AND (schedule_type <> 'RECURRING' OR duration_minutes > 0)",
            name="chk_mw_window_positive",
        ),
    )
    op.create_index("idx_mw_active_scope", "maintenance_windows", ["scope_type", "scope_id"])

    # ── alerts ─────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("alert_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_type", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "camera_id",
            sa.Integer(),
            sa.ForeignKey("cameras.camera_id", ondelete="NO ACTION"),
            nullable=False,
        ),
        sa.Column("zone_id", sa.Integer(), nullable=True),
        sa.Column("global_track_id", sa.Uuid(), nullable=True),
        sa.Column("person_id", sa.Integer(), nullable=True),
        sa.Column("triggered_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column(
            "acknowledged_by",
            sa.Integer(),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column(
            "suppressed_by_window_id",
            sa.Integer(),
            sa.ForeignKey("maintenance_windows.window_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "(acknowledged_at IS NULL OR acknowledged_at >= triggered_at)"
            " AND (resolved_at IS NULL OR resolved_at >= triggered_at)"
            " AND (resolved_at IS NULL OR acknowledged_at IS NULL"
            "      OR resolved_at >= acknowledged_at)",
            name="chk_alert_resolution_order",
        ),
    )
    op.create_index("ix_alerts_alert_type", "alerts", ["alert_type"])
    op.create_index("ix_alerts_triggered_at", "alerts", ["triggered_at"])

    # ── alert_routing ──────────────────────────────────────────────────
    op.create_table(
        "alert_routing",
        sa.Column("routing_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_type", sa.String(30), nullable=True),
        sa.Column("severity", sa.String(10), nullable=True),
        sa.Column("zone_id", sa.Integer(), nullable=True),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("target", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "channel IN ('EMAIL', 'SLACK', 'TELEGRAM', 'WEBHOOK', 'WEBSOCKET')",
            name="chk_routing_channel",
        ),
    )

    # ── alert_dispatches ───────────────────────────────────────────────
    _bigint = sa.BigInteger() if dialect == "postgresql" else sa.Integer()
    op.create_table(
        "alert_dispatches",
        sa.Column("dispatch_id", _bigint, primary_key=True, autoincrement=True),
        sa.Column(
            "alert_id",
            sa.Integer(),
            sa.ForeignKey("alerts.alert_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("target", sa.String(500), nullable=False),
        sa.Column("attempt_n", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "dispatched_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()" if dialect == "postgresql" else "CURRENT_TIMESTAMP"),
        ),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
    )
    op.create_index("idx_dispatches_alert", "alert_dispatches", ["alert_id"])

    # ── tracking_events ────────────────────────────────────────────────
    # Monthly-partitioned on PostgreSQL; plain table on SQLite.
    # Partition management (CREATE PARTITION FUNCTION equivalent) is handled
    # by the vms.scheduler cron job "create_partition" which runs on the 25th.
    _bigint2 = sa.BigInteger() if dialect == "postgresql" else sa.Integer()
    op.create_table(
        "tracking_events",
        sa.Column("event_id", _bigint2, primary_key=True, autoincrement=True),
        sa.Column(
            "camera_id",
            sa.Integer(),
            sa.ForeignKey("cameras.camera_id", ondelete="NO ACTION"),
            nullable=False,
        ),
        sa.Column("local_track_id", sa.String(50), nullable=False),
        sa.Column("global_track_id", sa.Uuid(), nullable=False),
        sa.Column(
            "person_id",
            sa.Integer(),
            sa.ForeignKey("persons.person_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("zone_id", sa.Integer(), nullable=True),
        sa.Column("event_ts", sa.DateTime(), nullable=False),
        sa.Column("ingest_ts", sa.DateTime(), nullable=False),
        sa.Column("bbox_x1", sa.Integer(), nullable=False),
        sa.Column("bbox_y1", sa.Integer(), nullable=False),
        sa.Column("bbox_x2", sa.Integer(), nullable=False),
        sa.Column("bbox_y2", sa.Integer(), nullable=False),
        sa.Column("floor_x", sa.Float(), nullable=True),
        sa.Column("floor_y", sa.Float(), nullable=True),
        sa.Column("seq_id", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("bbox_x2 > bbox_x1 AND bbox_y2 > bbox_y1", name="chk_bbox_valid"),
        sa.UniqueConstraint("camera_id", "local_track_id", "event_ts", name="uq_tracking_idem"),
    )
    op.create_index("ix_tracking_events_global_track_id", "tracking_events", ["global_track_id"])
    op.create_index("ix_tracking_events_person_id", "tracking_events", ["person_id"])
    op.create_index("ix_tracking_events_camera_id", "tracking_events", ["camera_id"])
    op.create_index("ix_tracking_events_event_ts", "tracking_events", ["event_ts"])

    # ── reid_matches ───────────────────────────────────────────────────
    _bigint3 = sa.BigInteger() if dialect == "postgresql" else sa.Integer()
    op.create_table(
        "reid_matches",
        sa.Column("reid_match_id", _bigint3, primary_key=True, autoincrement=True),
        sa.Column("global_track_id_1", sa.Uuid(), nullable=False),
        sa.Column("global_track_id_2", sa.Uuid(), nullable=False),
        sa.Column(
            "person_id",
            sa.Integer(),
            sa.ForeignKey("persons.person_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("event_ts", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_reid_global_track_1", "reid_matches", ["global_track_id_1"])
    op.create_index("ix_reid_global_track_2", "reid_matches", ["global_track_id_2"])
    op.create_index("ix_reid_person", "reid_matches", ["person_id"])

    # ── zone_presence ──────────────────────────────────────────────────
    _bigint4 = sa.BigInteger() if dialect == "postgresql" else sa.Integer()
    op.create_table(
        "zone_presence",
        sa.Column("presence_id", _bigint4, primary_key=True, autoincrement=True),
        sa.Column(
            "zone_id",
            sa.Integer(),
            sa.ForeignKey("zones.zone_id", ondelete="NO ACTION"),
            nullable=False,
        ),
        sa.Column("global_track_id", sa.Uuid(), nullable=False),
        sa.Column("entered_at", sa.DateTime(), nullable=False),
        sa.Column("exited_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "exited_at IS NULL OR exited_at >= entered_at",
            name="chk_presence_temporal",
        ),
        sa.UniqueConstraint("zone_id", "global_track_id", "entered_at", name="uq_zone_presence"),
    )
    op.create_index("ix_zp_zone_id", "zone_presence", ["zone_id"])
    op.create_index("ix_zp_global_track", "zone_presence", ["global_track_id"])

    # ── anomaly_detectors ──────────────────────────────────────────────
    op.create_table(
        "anomaly_detectors",
        sa.Column("detector_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_type", sa.String(30), nullable=False),
        sa.Column("class_path", sa.String(200), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()" if dialect == "postgresql" else "CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()" if dialect == "postgresql" else "CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("alert_type", name="uq_anomaly_alert_type"),
    )

    # ── person_clip_embeddings ─────────────────────────────────────────
    if dialect == "postgresql":
        op.create_table(
            "person_clip_embeddings",
            sa.Column("clip_emb_id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("global_track_id", sa.Uuid(), nullable=False),
            sa.Column(
                "camera_id",
                sa.Integer(),
                sa.ForeignKey("cameras.camera_id", ondelete="NO ACTION"),
                nullable=False,
            ),
            sa.Column("event_ts", sa.DateTime(), nullable=False),
            sa.Column("embedding", sa.Text(), nullable=False),
            sa.Column("snapshot_path", sa.String(500), nullable=False),
            sa.UniqueConstraint("global_track_id", "event_ts", name="uq_clip_track_ts"),
        )
        op.execute(
            "ALTER TABLE person_clip_embeddings ALTER COLUMN embedding TYPE vector(512) USING embedding::vector(512)"
        )
    else:
        op.create_table(
            "person_clip_embeddings",
            sa.Column("clip_emb_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("global_track_id", sa.Uuid(), nullable=False),
            sa.Column(
                "camera_id",
                sa.Integer(),
                sa.ForeignKey("cameras.camera_id", ondelete="NO ACTION"),
                nullable=False,
            ),
            sa.Column("event_ts", sa.DateTime(), nullable=False),
            sa.Column("embedding", sa.LargeBinary(), nullable=False),
            sa.Column("snapshot_path", sa.String(500), nullable=False),
            sa.UniqueConstraint("global_track_id", "event_ts", name="uq_clip_track_ts"),
        )
    op.create_index("ix_clip_ts", "person_clip_embeddings", ["event_ts"])
    op.create_index("ix_clip_global_track", "person_clip_embeddings", ["global_track_id"])

    # ── model_registry ─────────────────────────────────────────────────
    op.create_table(
        "model_registry",
        sa.Column("model_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("purpose", sa.String(50), nullable=False),
        sa.Column("fine_tunable", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()" if dialect == "postgresql" else "CURRENT_TIMESTAMP"),
        ),
    )

    # ── audit_log ──────────────────────────────────────────────────────
    _bigint5 = sa.BigInteger() if dialect == "postgresql" else sa.Integer()
    op.create_table(
        "audit_log",
        sa.Column("audit_id", _bigint5, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.String(50), nullable=True),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column(
            "event_ts",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()" if dialect == "postgresql" else "CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("idx_audit_ts", "audit_log", ["event_ts"])
    op.create_index("idx_audit_target", "audit_log", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("model_registry")
    op.drop_table("person_clip_embeddings")
    op.drop_table("anomaly_detectors")
    op.drop_table("zone_presence")
    op.drop_table("reid_matches")
    op.drop_table("tracking_events")
    op.drop_table("alert_dispatches")
    op.drop_table("alert_routing")
    op.drop_table("alerts")
    op.drop_table("maintenance_windows")
    op.drop_table("person_embeddings")
    op.drop_table("persons")
    op.drop_table("user_camera_permissions")
    op.drop_table("users")
    op.drop_table("zones")
    op.drop_table("cameras")
