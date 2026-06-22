"""add_camera_analytics_rtsp_url

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f7
Create Date: 2026-06-22

Adds:
  - cameras.analytics_rtsp_url (VARCHAR(500), nullable)
    Sub-stream URL for analytics ingestion (spec §6.7 dual-stream).
    When set, the ingestion worker opens this URL instead of rtsp_url.
    rtsp_url is kept for recording/clip use. Null = fall back to rtsp_url.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cameras",
        sa.Column("analytics_rtsp_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cameras", "analytics_rtsp_url")
