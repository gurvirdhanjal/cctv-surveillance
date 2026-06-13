"""GET /api/forensic/clips/{global_track_id} and GET /api/forensic/search (stub)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from vms.api.deps import get_db, require_role
from vms.api.schemas import ForensicClipItem, ForensicClipsResponse
from vms.config import get_settings
from vms.db.models import PersonClipEmbedding

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
    _user: dict[str, Any] = require_role("admin", "manager"),  # noqa: B008  # Any: user dict shape is opaque; role check enforced by require_role
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


@router.get("/forensic/search")
def forensic_search(
    q: str = Query(...),
    from_dt: datetime | None = Query(None, alias="from"),
    to_dt: datetime | None = Query(None, alias="to"),
    zone_id: int | None = Query(None),
    _user: dict[str, Any] = require_role("admin", "manager"),  # noqa: B008  # Any: user dict shape is opaque; role check enforced by require_role
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
