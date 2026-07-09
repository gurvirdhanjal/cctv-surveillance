"""/api/bookmarks (Phase 4P Task 8). Own-rows-only; guard+ roles."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db
from vms.api.schemas import BookmarkCreate, BookmarkResponse
from vms.db.models import Bookmark, Camera, UserCameraPermission
from vms.db.models import User as DBUser

router = APIRouter()


@router.get("/bookmarks", response_model=list[BookmarkResponse])
def list_bookmarks(
    camera_id: int | None = Query(default=None),
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[Bookmark]:
    query = select(Bookmark).where(Bookmark.user_id == int(user["sub"]))
    if camera_id is not None:
        query = query.where(Bookmark.camera_id == camera_id)
    return list(db.execute(query.order_by(Bookmark.created_at.desc())).scalars().all())


@router.post("/bookmarks", response_model=BookmarkResponse, status_code=status.HTTP_201_CREATED)
def create_bookmark(
    body: BookmarkCreate,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Bookmark:
    user_id = int(user["sub"])
    if db.get(DBUser, user_id) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Requesting user not found"
        )
    if db.get(Camera, body.camera_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    if user.get("role") != "admin":
        perm_camera_ids = (
            db.execute(
                select(UserCameraPermission.camera_id).where(
                    UserCameraPermission.user_id == user_id
                )
            )
            .scalars()
            .all()
        )
        # Zero rows = camera scoping not configured for this user -> unrestricted
        if perm_camera_ids and body.camera_id not in perm_camera_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="No permission for this camera"
            )

    bookmark = Bookmark(
        user_id=user_id,
        camera_id=body.camera_id,
        ts=body.ts,
        alert_id=body.alert_id,
        note=body.note,
    )
    db.add(bookmark)
    db.commit()
    db.refresh(bookmark)
    return bookmark


@router.delete("/bookmarks/{bookmark_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bookmark(
    bookmark_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Response:
    bookmark = db.get(Bookmark, bookmark_id)
    # 404 (not 403) for other users' rows -- existence must not leak
    if bookmark is None or bookmark.user_id != int(user["sub"]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bookmark not found")
    db.delete(bookmark)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
