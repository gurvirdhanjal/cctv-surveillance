"""/api/users CRUD (Phase 4P Task 7). Admin only; soft-deactivate, never delete."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db, hash_password
from vms.api.schemas import PasswordResetRequest, UserCreate, UserResponse, UserUpdate
from vms.db.audit import write_audit_event
from vms.db.models import Camera, User, UserCameraPermission

router = APIRouter()


def _require_admin(user: dict[str, Any]) -> int:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return int(user["sub"])


def _camera_ids(db: Session, user_id: int) -> list[int]:
    return list(
        db.execute(
            select(UserCameraPermission.camera_id)
            .where(UserCameraPermission.user_id == user_id)
            .order_by(UserCameraPermission.camera_id)
        ).scalars()
    )


def _response(db: Session, user: User) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        camera_ids=_camera_ids(db, user.user_id),
    )


def _get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


def _guard_last_active_admin(db: Session, target: User) -> None:
    """409 when the mutation would leave zero active admins."""
    if target.role != "admin" or not target.is_active:
        return
    other_admins: int = db.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == "admin", User.is_active.is_(True), User.user_id != target.user_id)
    ).scalar_one()
    if other_admins == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot demote or deactivate the last active admin",
        )


def _replace_camera_permissions(db: Session, user_id: int, camera_ids: list[int]) -> None:
    known = set(
        db.execute(select(Camera.camera_id).where(Camera.camera_id.in_(camera_ids))).scalars()
    )
    unknown = [c for c in camera_ids if c not in known]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown camera ids: {unknown}",
        )
    db.execute(delete(UserCameraPermission).where(UserCameraPermission.user_id == user_id))
    for camera_id in camera_ids:
        db.add(UserCameraPermission(user_id=user_id, camera_id=camera_id))
    db.flush()


@router.get("/users", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[UserResponse]:
    _require_admin(user)
    rows = db.execute(select(User).order_by(User.username)).scalars().all()
    return [_response(db, u) for u in rows]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> UserResponse:
    actor_id = _require_admin(user)
    clashes = [User.username == body.username]
    if body.email is not None:
        clashes.append(User.email == body.email)
    duplicate = db.execute(
        select(User.user_id).where(clashes[0] if len(clashes) == 1 else clashes[0] | clashes[1])
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username or email already exists"
        )

    new_user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(new_user)
    db.flush()
    write_audit_event(
        db,
        event_type="USER_CREATED",
        actor_user_id=actor_id,
        target_type="user",
        target_id=str(new_user.user_id),
        payload=json.dumps({"username": body.username, "role": body.role}),
    )
    return _response(db, new_user)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> UserResponse:
    actor_id = _require_admin(user)
    target = _get_user_or_404(db, user_id)

    demoting = body.role is not None and body.role != target.role and target.role == "admin"
    deactivating = body.is_active is False and target.is_active
    if demoting and target.user_id == actor_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="You cannot demote yourself"
        )
    if demoting or deactivating:
        _guard_last_active_admin(db, target)

    changes: dict[str, Any] = {}
    if body.email is not None:
        target.email = body.email
        changes["email"] = body.email
    if body.role is not None:
        target.role = body.role
        changes["role"] = body.role
    if body.is_active is not None:
        target.is_active = body.is_active
        changes["is_active"] = body.is_active
    if body.camera_ids is not None:
        _replace_camera_permissions(db, target.user_id, body.camera_ids)
        changes["camera_ids"] = body.camera_ids

    write_audit_event(
        db,
        event_type="USER_DEACTIVATED" if deactivating else "USER_UPDATED",
        actor_user_id=actor_id,
        target_type="user",
        target_id=str(target.user_id),
        payload=json.dumps(changes),
    )
    return _response(db, target)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Response:
    actor_id = _require_admin(user)
    target = _get_user_or_404(db, user_id)
    _guard_last_active_admin(db, target)
    target.is_active = False
    write_audit_event(
        db,
        event_type="USER_DEACTIVATED",
        actor_user_id=actor_id,
        target_type="user",
        target_id=str(target.user_id),
        payload=json.dumps({"is_active": False}),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/reset-password", response_model=UserResponse)
def reset_password(
    user_id: int,
    body: PasswordResetRequest,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> UserResponse:
    actor_id = _require_admin(user)
    target = _get_user_or_404(db, user_id)
    target.password_hash = hash_password(body.new_password)
    write_audit_event(
        db,
        event_type="USER_PASSWORD_RESET",
        actor_user_id=actor_id,
        target_type="user",
        target_id=str(target.user_id),
        payload=None,
    )
    return _response(db, target)
