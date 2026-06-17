"""storage_key_semantics_thumbnail_and_snapshot_paths

Converts persons.thumbnail_path and person_clip_embeddings.snapshot_path from
absolute filesystem paths to relative storage keys.

Relative keys use the format: {prefix}/{YYYY}/{MM}/{DD}/{uuid}.jpg
  thumbnails/... for persons.thumbnail_path
  snapshots/...  for person_clip_embeddings.snapshot_path

No DDL change — both columns remain String(500). The upgrade() data migration
strips any absolute-path prefix, keeping only the portion starting at
'thumbnails/' or 'snapshots/'. Rows already using relative keys are left alone.

Revision ID: 4d08355b1fef
Revises: a1b2c3d4e5f6
Create Date: 2026-05-28 21:03:36.259205
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4d08355b1fef"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert persons.thumbnail_path to relative key.
    # Rows already starting with 'thumbnails/' or 'snapshots/' are unchanged.
    op.execute(
        """
        UPDATE persons
        SET thumbnail_path = SUBSTRING(
            thumbnail_path
            FROM POSITION('thumbnails/' IN thumbnail_path)
        )
        WHERE thumbnail_path IS NOT NULL
          AND thumbnail_path NOT LIKE 'thumbnails/%'
          AND thumbnail_path NOT LIKE 'snapshots/%'
          AND POSITION('thumbnails/' IN thumbnail_path) > 0
        """
    )

    # Convert person_clip_embeddings.snapshot_path to relative key.
    op.execute(
        """
        UPDATE person_clip_embeddings
        SET snapshot_path = SUBSTRING(
            snapshot_path
            FROM POSITION('snapshots/' IN snapshot_path)
        )
        WHERE snapshot_path NOT LIKE 'thumbnails/%'
          AND snapshot_path NOT LIKE 'snapshots/%'
          AND POSITION('snapshots/' IN snapshot_path) > 0
        """
    )


def downgrade() -> None:
    # The path→key conversion is irreversible without knowing the original base
    # directory. Downgrade is intentionally a no-op; relative keys remain valid
    # if the migration is rolled back (they simply won't be found on disk until
    # the admin re-maps them).
    pass
