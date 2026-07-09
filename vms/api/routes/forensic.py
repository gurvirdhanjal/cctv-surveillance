"""Forensic endpoints: clips, search (stub) and clip-export jobs."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db, require_role
from vms.api.schemas import (
    ExportJobCreate,
    ExportJobResponse,
    ForensicClipItem,
    ForensicClipsResponse,
)
from vms.config import get_settings
from vms.db.audit import write_audit_event
from vms.db.models import Camera, ExportJob, PersonClipEmbedding, UserCameraPermission
from vms.db.models import User as DBUser

_log = logging.getLogger(__name__)
_settings = get_settings()

router = APIRouter()


def _snapshot_url(path: str) -> str:
    """Return a URL for a snapshot_path storage key."""
    if path.startswith(("http://", "https://")):
        return path
    return f"/media/{path}"


@router.get("/forensic/clips/{global_track_id}", response_model=ForensicClipsResponse)
def get_forensic_clips(
    global_track_id: str,
    around_ts: datetime | None = Query(None),  # noqa: B008
    window_seconds: int = Query(
        _settings.forensic_window_default_s,
        ge=_settings.forensic_window_min_s,
        le=_settings.forensic_window_max_s,
    ),
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[
        str, Any
    ] = require_role(  # noqa: B008  # Any: user dict shape is opaque; role check enforced by require_role
        "admin", "manager"
    ),
) -> ForensicClipsResponse:
    try:
        track_uuid = uuid.UUID(global_track_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="global_track_id must be a valid UUID",
        ) from exc

    q = db.query(PersonClipEmbedding).filter(PersonClipEmbedding.global_track_id == track_uuid)

    if around_ts is not None:
        delta = timedelta(seconds=window_seconds)
        q = q.filter(
            PersonClipEmbedding.event_ts >= around_ts - delta,
            PersonClipEmbedding.event_ts <= around_ts + delta,
        )

    clips = q.order_by(PersonClipEmbedding.event_ts.asc()).all()

    return ForensicClipsResponse(
        clips=[
            ForensicClipItem(
                clip_emb_id=c.clip_emb_id,
                global_track_id=str(c.global_track_id),
                camera_id=c.camera_id,
                event_ts=c.event_ts,
                snapshot_url=_snapshot_url(c.snapshot_path),
            )
            for c in clips
        ],
        total=len(clips),
    )


def _job_response(job: ExportJob) -> ExportJobResponse:
    return ExportJobResponse(
        job_id=str(job.id),
        state=job.state,
        camera_id=job.camera_id,
        from_ts=job.from_ts,
        to_ts=job.to_ts,
        created_at=job.created_at,
    )


@router.post(
    "/forensic/export",
    response_model=ExportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_export_job(
    body: ExportJobCreate,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> ExportJobResponse:
    settings = get_settings()
    if body.from_ts >= body.to_ts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'from_ts' must be earlier than 'to_ts'",
        )
    window_s = (body.to_ts - body.from_ts).total_seconds()
    if window_s > settings.export_max_window_s:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"export window must be <= {settings.export_max_window_s}s",
        )

    if db.get(Camera, body.camera_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")

    requester_id = int(user["sub"])
    if db.get(DBUser, requester_id) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requesting user not found"
        )
    if user.get("role") != "admin":
        perm_camera_ids = (
            db.execute(
                select(UserCameraPermission.camera_id).where(
                    UserCameraPermission.user_id == requester_id
                )
            )
            .scalars()
            .all()
        )
        # Zero rows = camera scoping not configured for this user -> unrestricted
        if perm_camera_ids and body.camera_id not in perm_camera_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No permission for this camera",
            )

    job = ExportJob(
        requested_by=requester_id,
        camera_id=body.camera_id,
        from_ts=body.from_ts,
        to_ts=body.to_ts,
        reason=body.reason,
    )
    db.add(job)
    db.flush()
    # write_audit_event commits internally -- do not commit separately
    write_audit_event(
        db,
        event_type="CLIP_EXPORT_REQUESTED",
        actor_user_id=requester_id,
        target_type="export_job",
        target_id=str(job.id),
        payload=json.dumps(
            {
                "camera_id": body.camera_id,
                "from": body.from_ts.isoformat(),
                "to": body.to_ts.isoformat(),
                "reason": body.reason,
            }
        ),
    )
    return _job_response(job)


@router.get("/forensic/export/{job_id}", response_model=ExportJobResponse)
def get_export_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> ExportJobResponse:
    job = db.get(ExportJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found")
    if user.get("role") != "admin" and job.requested_by != int(user["sub"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the job owner")
    return _job_response(job)


@router.get("/forensic/search")
def forensic_search(
    q: str = Query(...),
    from_dt: datetime | None = Query(None, alias="from"),  # noqa: B008
    to_dt: datetime | None = Query(None, alias="to"),  # noqa: B008
    zone_id: int | None = Query(None),
    _user: dict[
        str, Any
    ] = require_role(  # noqa: B008  # Any: user dict shape is opaque; role check enforced by require_role
        "admin", "manager"
    ),
) -> None:
    # Requires CLIP-ViT-B/32 ONNX text encoder (VMS_CLIP_MODEL) and the CLIP
    # inference pipeline writing to person_clip_embeddings. Neither exists yet.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            "CLIP text-encoder not configured. "
            "Set VMS_CLIP_MODEL and enable CLIP inference pipeline to activate this endpoint."
        ),
    )
