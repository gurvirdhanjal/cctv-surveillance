"""add_export_jobs

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-07-09

Clip-export job queue (Phase 4P Task 6). The export worker lands in the
recording spec; this phase only queues jobs (202-queued contract).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "requested_by", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False
        ),
        sa.Column(
            "camera_id",
            sa.Integer(),
            sa.ForeignKey("cameras.camera_id", ondelete="NO ACTION"),
            nullable=False,
        ),
        sa.Column("from_ts", sa.DateTime(), nullable=False),
        sa.Column("to_ts", sa.DateTime(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("state", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "state IN ('QUEUED', 'RUNNING', 'COMPLETE', 'FAILED')",
            name="chk_export_job_state",
        ),
        sa.CheckConstraint("to_ts > from_ts", name="chk_export_window_valid"),
    )


def downgrade() -> None:
    op.drop_table("export_jobs")
