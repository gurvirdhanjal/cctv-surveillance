"""Delete the 5 placeholder cameras (IDs 11-15) that have cam0N.plant.local hostnames.

These were seeded as demo data. This script deletes their associated alerts
(and cascading dispatches) first, then removes the cameras.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("VMS_DB_URL", "postgresql://vms:vms@localhost:5432/vms")
os.environ.setdefault("VMS_JWT_SECRET", "dev-secret")

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

DB_URL = os.environ["VMS_DB_URL"]
PLACEHOLDER_IDS = [11, 12, 13, 14, 15]


def main() -> None:
    from vms.db.models import Camera

    engine = create_engine(DB_URL)
    with Session(engine) as session:
        # Step 1: Delete alerts (and their dispatches via cascade) for these cameras
        result = session.execute(
            text("DELETE FROM alerts WHERE camera_id = ANY(:ids)"),
            {"ids": PLACEHOLDER_IDS},
        )
        if result.rowcount:
            print(f"Deleted {result.rowcount} demo alert(s) associated with placeholder cameras")

        # Step 2: Delete the cameras
        deleted = 0
        for cam_id in PLACEHOLDER_IDS:
            cam = session.get(Camera, cam_id)
            if cam is None:
                print(f"Camera {cam_id}: not found (already deleted?)")
                continue
            print(f"Deleting camera {cam_id}: '{cam.name}'")
            session.delete(cam)
            deleted += 1

        session.commit()
        if deleted:
            print(f"Done — deleted {deleted} placeholder camera(s).")
        else:
            print("Nothing to delete.")


if __name__ == "__main__":
    main()
