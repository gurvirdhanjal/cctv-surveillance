"""Authentication routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from vms.api.deps import create_access_token, get_db, verify_password
from vms.api.schemas import TokenRequest, TokenResponse
from vms.db.audit import write_audit_event
from vms.db.models import User

router = APIRouter()

_INVALID = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/auth/token", response_model=TokenResponse)
def login(body: TokenRequest, db: Session = Depends(get_db)) -> Any:  # noqa: B008
    user: User | None = db.query(User).filter_by(username=body.username).first()

    if user is None or not verify_password(body.password, user.password_hash):
        write_audit_event(
            db,
            event_type="LOGIN_FAILURE",
            payload=f"username={body.username}",
        )
        raise _INVALID

    if not user.is_active:
        raise _INVALID

    write_audit_event(db, event_type="LOGIN_SUCCESS", actor_user_id=user.user_id)

    return TokenResponse(access_token=create_access_token(user.user_id, user.role))
