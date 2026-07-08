"""add_camera_hierarchy_fields

Revision ID: c3d4e5f6a7b8
Revises: a0ae6d1f0eec
Create Date: 2026-07-08

Adds §Q site hierarchy columns to the cameras table.
All three are nullable so existing cameras are unaffected.
Frontend groups NULL values as "Default Site" / "Main Building" / etc.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "a0ae6d1f0eec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("site_name", sa.String(200), nullable=True))
    op.add_column("cameras", sa.Column("building_name", sa.String(200), nullable=True))
    op.add_column("cameras", sa.Column("floor_name", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("cameras", "floor_name")
    op.drop_column("cameras", "building_name")
    op.drop_column("cameras", "site_name")
