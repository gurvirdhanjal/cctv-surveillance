"""add_floor_plans_and_homography_calibration

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-07-09

Minimal floor_plans registry + camera calibration metadata columns
(Phase 4P Task 8b, model-stack spec §8.2.1).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "floor_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("image_path", sa.String(500), nullable=False),
        sa.Column("scale_m_per_px", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("scale_m_per_px > 0", name="chk_floor_plan_scale"),
    )
    op.add_column("cameras", sa.Column("homography_calibration", sa.Text(), nullable=True))
    op.add_column(
        "cameras",
        sa.Column(
            "floor_plan_id",
            sa.Integer(),
            sa.ForeignKey("floor_plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("cameras", "floor_plan_id")
    op.drop_column("cameras", "homography_calibration")
    op.drop_table("floor_plans")
