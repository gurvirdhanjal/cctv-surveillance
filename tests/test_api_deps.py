"""Tests for JWT helpers in vms.api.deps."""

from __future__ import annotations

import pytest
from jose import JWTError

from vms.api.deps import create_access_token, decode_access_token


def test_create_and_decode_token_round_trip() -> None:
    token = create_access_token(user_id=42, role="guard")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "guard"


def test_decode_invalid_token_raises() -> None:
    with pytest.raises(JWTError):
        decode_access_token("not.a.valid.token")
