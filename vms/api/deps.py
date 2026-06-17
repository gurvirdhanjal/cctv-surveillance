"""FastAPI dependencies: database session, JWT auth."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt  # type: ignore[import-untyped]
from passlib.context import CryptContext  # type: ignore[import-untyped]

from vms.config import get_settings
from vms.db.session import SessionLocal

_api_redis: aioredis.Redis | None = None

# Process-level shared state for inspection routes.
_orchestrator_health: dict[str, dict[str, object]] = {}


def set_orchestrator_health(snapshot: dict[str, dict[str, object]]) -> None:
    """Called by the orchestrator process every N seconds."""
    _orchestrator_health.clear()
    _orchestrator_health.update(snapshot)


def get_orchestrator_health() -> dict[str, dict[str, object]]:
    return dict(_orchestrator_health)


def get_api_redis() -> aioredis.Redis:
    """Return a process-level Redis client for publishing faiss_dirty events."""
    global _api_redis
    if _api_redis is None:
        _api_redis = aioredis.from_url(  # type: ignore[no-untyped-call]
            get_settings().redis_url, decode_responses=True
        )
    return _api_redis


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return bool(_pwd_context.verify(plain, hashed))


def hash_password(password: str) -> str:
    return str(_pwd_context.hash(password))


_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_db() -> Generator[Any, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
    }
    return str(jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm))


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return dict(jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]))


def require_role(*allowed_roles: str) -> Any:
    """Return a FastAPI Depends that allows only the specified roles.

    Usage: ``user: dict = require_role("admin", "super_admin")``
    FastAPI resolves the inner _check function; the outer Depends wrapper
    tells FastAPI to treat the return value as a dependency, not a literal.
    """

    def _check(
        current_user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    ) -> dict[str, Any]:
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return Depends(_check)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),  # noqa: B008
) -> dict[str, Any]:
    if credentials is None:
        raise _UNAUTHORIZED
    try:
        return decode_access_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
