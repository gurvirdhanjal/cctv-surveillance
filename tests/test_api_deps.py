"""Tests for JWT helpers in vms.api.deps."""

from __future__ import annotations

import time

import pytest
from fastapi import HTTPException
from jose import JWTError, jwt

from vms.api.deps import create_access_token, decode_access_token, get_current_user
from vms.config import get_settings


def test_create_and_decode_token_round_trip() -> None:
    token = create_access_token(user_id=42, role="guard")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "guard"


def test_decode_invalid_token_raises() -> None:
    with pytest.raises(JWTError):
        decode_access_token("not.a.valid.token")


def test_token_contains_exp_claim() -> None:
    token = create_access_token(user_id=1, role="guard")
    payload = decode_access_token(token)
    assert "exp" in payload
    assert payload["exp"] > int(time.time())


def test_expired_token_raises_401() -> None:
    from fastapi.security import HTTPAuthorizationCredentials

    settings = get_settings()
    past_payload = {"sub": "1", "role": "guard", "exp": int(time.time()) - 10}
    token = jwt.encode(past_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert exc_info.value.status_code == 401
