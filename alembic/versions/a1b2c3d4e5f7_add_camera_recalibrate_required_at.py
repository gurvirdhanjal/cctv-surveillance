"""add_camera_recalibrate_required_at

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-06-13

Adds:
  - cameras.recalibrate_required_at (TIMESTAMP WITHOUT TIME ZONE, nullable)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cameras",
        sa.Column("recalibrate_required_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cameras", "recalibrate_required_at")
