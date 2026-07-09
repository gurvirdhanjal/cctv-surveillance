"""add_camera_status_events

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-07-09

camera_status_events: online/offline transition history for real uptime
(Phase 4P Task 2; premium-polish spec §8.2 — uptime never from is_active).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "camera_status_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "camera_id",
            sa.Integer(),
            sa.ForeignKey("cameras.camera_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('online', 'offline')", name="chk_camera_status_event"),
    )
    op.create_index(
        "ix_camera_status_events_camera_at",
        "camera_status_events",
        ["camera_id", "at"],
    )


def downgrade() -> None:
    op.drop_index("ix_camera_status_events_camera_at", table_name="camera_status_events")
    op.drop_table("camera_status_events")
