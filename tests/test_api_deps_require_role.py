"""Tests for require_role dependency."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vms.api.deps import create_access_token, require_role


def _make_app(allowed: tuple[str, ...]) -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    def protected(user: dict = require_role(*allowed)):  # type: ignore[type-arg]  # noqa: B008
        return {"role": user["role"]}

    return app


def test_require_role_allows_matching_role() -> None:
    client = TestClient(_make_app(("admin",)))
    token = create_access_token(1, "admin")
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"


def test_require_role_rejects_wrong_role() -> None:
    client = TestClient(_make_app(("admin",)))
    token = create_access_token(1, "guard")
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_require_role_allows_multiple_roles() -> None:
    client = TestClient(_make_app(("admin", "super_admin")))
    for role in ("admin", "super_admin"):
        token = create_access_token(1, role)
        resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, f"Expected 200 for role={role}"


def test_require_role_rejects_no_token() -> None:
    client = TestClient(_make_app(("admin",)))
    resp = client.get("/protected")
    assert resp.status_code == 401


def test_require_role_rejects_expired_token() -> None:
    client = TestClient(_make_app(("admin",)))
    resp = client.get("/protected", headers={"Authorization": "Bearer not.a.valid.token"})
    assert resp.status_code == 401
