"""add_analytics_head_count_hourly

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-09

Hourly head-count rollup table (Phase 4P Task 4). zone_id NULL = plant-total
row; UNIQUE uses NULLS NOT DISTINCT so the plant row upserts like zone rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analytics_head_count_hourly",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("bucket_start", sa.DateTime(), nullable=False),
        sa.Column("zone_id", sa.Integer(), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.CheckConstraint("count >= 0", name="chk_head_count_nonneg"),
        sa.UniqueConstraint(
            "bucket_start",
            "zone_id",
            name="uq_head_count_bucket_zone",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_head_count_hourly_bucket",
        "analytics_head_count_hourly",
        ["bucket_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_head_count_hourly_bucket", table_name="analytics_head_count_hourly")
    op.drop_table("analytics_head_count_hourly")
