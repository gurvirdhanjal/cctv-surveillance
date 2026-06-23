"""Tests for Socket.io JWT authentication — §10 connect handler."""

from __future__ import annotations

import pytest

from vms.api.deps import create_access_token
from vms.api.realtime.server import _validate_connect


async def test_socket_connect_requires_valid_jwt() -> None:
    with pytest.raises(ConnectionRefusedError):
        await _validate_connect(None)


async def test_socket_connect_rejects_empty_auth() -> None:
    with pytest.raises(ConnectionRefusedError):
        await _validate_connect({})


async def test_socket_connect_rejects_invalid_token() -> None:
    with pytest.raises(ConnectionRefusedError):
        await _validate_connect({"token": "this.is.garbage"})


async def test_socket_connect_accepts_valid_jwt() -> None:
    token = create_access_token(7, "guard")
    user = await _validate_connect({"token": token})
    assert user["sub"] == "7"
    assert user["role"] == "guard"


async def test_socket_connect_accepts_admin_jwt() -> None:
    token = create_access_token(1, "admin")
    user = await _validate_connect({"token": token})
    assert user["role"] == "admin"
