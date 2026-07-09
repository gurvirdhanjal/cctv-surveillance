"""Homography calibration API (Phase 4P Task 8b, model-stack spec §8.2.1).

The server recomputes the matrix from point pairs with cv2.findHomography(RANSAC);
any client-supplied matrix is ignored. Stored format matches
vms.identity.homography.project_to_floor: row-major 3x3 JSON.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db
from vms.api.schemas import (
    HomographyCalibrateRequest,
    HomographyPointPair,
    HomographyResponse,
)
from vms.config import get_settings
from vms.db.audit import write_audit_event
from vms.db.models import Camera, FloorPlan, UserCameraPermission
from vms.db.models import User as DBUser

router = APIRouter()


def _get_camera_or_404(db: Session, camera_id: int) -> Camera:
    cam = db.get(Camera, camera_id)
    if cam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return cam


def _compute_homography(
    pairs: list[HomographyPointPair], max_rms_px: float
) -> tuple[np.ndarray, float]:
    """RANSAC homography + reprojection RMS over ALL pairs. 422 on degenerate/bad fits."""
    image_pts = np.array([p.image for p in pairs], dtype=np.float32)
    floor_pts = np.array([p.floor for p in pairs], dtype=np.float32)
    matrix, _mask = cv2.findHomography(image_pts, floor_pts, cv2.RANSAC)
    if matrix is None or not np.isfinite(matrix).all():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Point pairs are degenerate (collinear?) — spread them across the floor",
        )
    projected = cv2.perspectiveTransform(image_pts.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    rms = float(np.sqrt(np.mean(np.sum((projected - floor_pts) ** 2, axis=1))))
    if rms > max_rms_px:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Reprojection RMS {rms:.1f}px exceeds limit {max_rms_px}px — recheck pairs",
        )
    return matrix, rms


@router.put("/cameras/{camera_id}/homography", response_model=HomographyResponse)
def calibrate_homography(
    camera_id: int,
    body: HomographyCalibrateRequest,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> HomographyResponse:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    cam = _get_camera_or_404(db, camera_id)
    if body.floor_plan_id is not None and db.get(FloorPlan, body.floor_plan_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown floor_plan_id"
        )

    matrix, rms = _compute_homography(body.point_pairs, get_settings().homography_max_rms_px)
    calibrated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    actor_id: int | None = int(user["sub"])
    if db.get(DBUser, actor_id) is None:
        actor_id = None

    cam.homography_matrix = json.dumps(matrix.flatten().tolist())
    cam.homography_calibration = json.dumps(
        {
            "point_pairs": [p.model_dump() for p in body.point_pairs],
            "rms_error_px": rms,
            "calibrated_at": calibrated_at.isoformat(),
            "calibrated_by": actor_id,
            "floor_plan_id": body.floor_plan_id,
        }
    )
    if body.floor_plan_id is not None:
        cam.floor_plan_id = body.floor_plan_id
    cam.recalibrate_required_at = None

    write_audit_event(
        db,
        event_type="CAMERA_CALIBRATED",
        actor_user_id=actor_id,
        target_type="camera",
        target_id=str(camera_id),
        payload=json.dumps(
            {
                "rms_error_px": rms,
                "pairs": len(body.point_pairs),
                "floor_plan_id": body.floor_plan_id,
            }
        ),
    )
    return HomographyResponse(
        matrix=list(matrix.flatten()),
        point_pairs=body.point_pairs,
        rms_error_px=rms,
        floor_plan_id=body.floor_plan_id,
        calibrated_at=calibrated_at,
        stale=False,
    )


@router.get("/cameras/{camera_id}/homography", response_model=HomographyResponse)
def get_homography(
    camera_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> HomographyResponse:
    cam = _get_camera_or_404(db, camera_id)
    if user.get("role") != "admin":
        perm_camera_ids = (
            db.execute(
                select(UserCameraPermission.camera_id).where(
                    UserCameraPermission.user_id == int(user["sub"])
                )
            )
            .scalars()
            .all()
        )
        # Zero rows = camera scoping not configured for this user -> unrestricted
        if perm_camera_ids and camera_id not in perm_camera_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="No permission for this camera"
            )
    if cam.homography_matrix is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Camera has not been calibrated"
        )

    meta: dict[str, Any] = (
        json.loads(cam.homography_calibration) if cam.homography_calibration else {}
    )
    calibrated_at_raw = meta.get("calibrated_at")
    return HomographyResponse(
        matrix=json.loads(cam.homography_matrix),
        point_pairs=[HomographyPointPair(**p) for p in meta.get("point_pairs", [])] or None,
        rms_error_px=meta.get("rms_error_px"),
        floor_plan_id=cam.floor_plan_id,
        calibrated_at=datetime.fromisoformat(calibrated_at_raw) if calibrated_at_raw else None,
        stale=cam.recalibrate_required_at is not None,
    )
