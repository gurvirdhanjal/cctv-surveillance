"""phase2a_add_homography_adjacent_zones

Revision ID: 5b4fe0f76497
Revises: 0001
Create Date: 2026-05-14 14:03:43.816363

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b4fe0f76497'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("homography_matrix", sa.Text(), nullable=True))
    op.add_column("zones", sa.Column("adjacent_zone_ids", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("zones", "adjacent_zone_ids")
    op.drop_column("cameras", "homography_matrix")
