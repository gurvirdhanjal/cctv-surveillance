"""add_bookmarks

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-07-09

Per-user camera/timestamp bookmarks (Phase 4P Task 8).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bookmarks",
        sa.Column("bookmark_id", sa.Integer(), autoincrement=True, primary_key=True),
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
        sa.Column("ts", sa.DateTime(), nullable=False),
        sa.Column(
            "alert_id",
            sa.Integer(),
            sa.ForeignKey("alerts.alert_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_bookmarks_user_camera", "bookmarks", ["user_id", "camera_id"])


def downgrade() -> None:
    op.drop_index("ix_bookmarks_user_camera", table_name="bookmarks")
    op.drop_table("bookmarks")
