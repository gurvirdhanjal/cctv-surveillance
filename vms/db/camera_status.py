"""Camera status transition writer (Phase 4P Task 2).

Records online/offline transitions in camera_status_events. The uptime KPI
(GET /api/analytics/kpi) is computed from this history, never from is_active.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from vms.db.models import CameraStatusEvent


def record_camera_status_transition(session: Session, *, camera_id: int, status: str) -> bool:
    """Insert a status event only when it differs from the camera's latest one.

    The first-ever call for a camera writes a baseline row. Returns True when a
    row was written. The caller owns the commit.
    """
    last = session.execute(
        select(CameraStatusEvent.status)
        .where(CameraStatusEvent.camera_id == camera_id)
        .order_by(CameraStatusEvent.at.desc(), CameraStatusEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last == status:
        return False
    session.add(
        CameraStatusEvent(
            camera_id=camera_id,
            status=status,
            at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    )
    return True
