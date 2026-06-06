# Camera Configuration API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: NOT STARTED**

**Goal:** Deliver the full per-camera configuration stack — `shutter_type` DB column, ShutterProfile config resolver, 8 camera API endpoints (CRUD + hardware + overrides + resolved-config + profile stub), and a `require_role` auth helper — so every camera setting is configurable via the Admin/Super Admin frontend (Phase 4) backed by a solid, audited backend.

**Architecture:** New `vms/api/routes/cameras.py` holds all 8 endpoints. A new `vms/inference/shutter_profile.py` module owns the 5-level config resolution hierarchy (manual override → shutter adjustment → detector config → env var → hard-coded default) and is the single source of truth for the `GET /api/cameras/{id}/resolved-config` response. `PATCH /hardware` and `PATCH /overrides` both write to `audit_log` and publish `camera_config_changed:{id}` to Redis for future InferenceEngine hot-reload. Frontend (Phase 4 `/admin/cameras/{id}`) consumes all these endpoints — that UI work is out of scope here.

**Tech Stack:** FastAPI, SQLAlchemy 2 mapped_column, Alembic, Pydantic v2, aioredis, pytest-asyncio, httpx ASGITransport

**Spec refs:**
- `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` §B, §L.3, §L.3.1, §L.4, §J
- `docs/superpowers/specs/2026-05-01-vms-frontend-design.md` §9 `<CameraDetail />`

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `vms/db/models.py` | Add `shutter_type` field to `Camera` |
| Create | `alembic/versions/<rev>_camera_shutter_and_overrides.py` | Add `shutter_type` + `model_overrides` columns |
| Modify | `vms/api/deps.py` | Add `require_role(*roles)` dependency factory |
| Modify | `vms/api/schemas.py` | Add all camera schemas + `ResolvedConfigResponse` |
| Create | `vms/inference/shutter_profile.py` | `ShutterAdjustment`, `resolve_camera_config()` |
| Create | `vms/api/routes/cameras.py` | All 8 camera endpoints |
| Modify | `vms/api/main.py` | Register cameras router |
| Create | `tests/test_db_models_cameras.py` | Camera ORM + shutter_type tests |
| Create | `tests/test_inference_shutter_profile.py` | ShutterProfile resolver tests |
| Create | `tests/test_api_cameras.py` | All endpoint tests |

---

## Task 1: DB Migration — add `shutter_type` and `model_overrides` columns

`model_overrides` is in the ORM but was never migrated (Phase 3 addition per spec §L.3). Add both columns in one migration.

**Files:**
- Modify: `vms/db/models.py`
- Create: `alembic/versions/<rev>_camera_shutter_and_overrides.py`
- Create: `tests/test_db_models_cameras.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_db_models_cameras.py`:

```python
"""Tests for Camera ORM — shutter_type and model_overrides fields."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vms.db.models import Camera


def _camera(**kwargs) -> Camera:  # type: ignore[no-untyped-def]
    defaults = {"name": "Test Cam", "rtsp_url": "rtsp://host/stream", "capability_tier": "FULL"}
    defaults.update(kwargs)
    return Camera(**defaults)


def test_camera_shutter_type_defaults_to_unknown(db_session: Session) -> None:
    cam = _camera()
    db_session.add(cam)
    db_session.flush()
    assert cam.shutter_type == "unknown"


def test_camera_shutter_type_accepts_valid_values(db_session: Session) -> None:
    for val in ("rolling", "global", "unknown"):
        cam = _camera(name=f"cam_{val}", shutter_type=val)
        db_session.add(cam)
    db_session.flush()


def test_camera_shutter_type_rejects_invalid_value(db_session: Session) -> None:
    cam = _camera(shutter_type="ccd")
    db_session.add(cam)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_camera_model_overrides_defaults_to_none(db_session: Session) -> None:
    cam = _camera()
    db_session.add(cam)
    db_session.flush()
    assert cam.model_overrides is None


def test_camera_model_overrides_stores_json_string(db_session: Session) -> None:
    payload = '{"models": {"face_embedder": "adaface_ir50_acme"}, "thresholds": {}}'
    cam = _camera(model_overrides=payload)
    db_session.add(cam)
    db_session.flush()
    db_session.refresh(cam)
    assert cam.model_overrides == payload
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_db_models_cameras.py -v
```

Expected: FAIL — `AttributeError: type object 'Camera' has no attribute 'shutter_type'`

- [ ] **Step 3: Add `shutter_type` to the Camera ORM**

In `vms/db/models.py`, find the `Camera` class. Add `shutter_type` after `profiled_at` and add `model_overrides` if not present, then add the CHECK constraint:

```python
class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        CheckConstraint("capability_tier IN ('FULL', 'MID', 'LOW')", name="chk_camera_tier"),
        CheckConstraint(
            "shutter_type IN ('rolling', 'global', 'unknown')", name="chk_camera_shutter"
        ),
    )

    camera_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rtsp_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    capability_tier: Mapped[str] = mapped_column(String(10), nullable=False, default="FULL")
    profile_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    profiled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shutter_type: Mapped[str] = mapped_column(String(10), nullable=False, default="unknown")
    model_overrides: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_group: Mapped[int | None] = mapped_column(Integer, nullable=True)
    homography_matrix: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Generate the Alembic migration**

```
alembic revision -m "camera_shutter_and_overrides"
```

This prints the new revision filename. Open it and replace the body with:

```python
"""camera_shutter_and_overrides

Revision ID: <generated>
Revises: <previous head>
Create Date: 2026-06-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column(
        "cameras",
        sa.Column(
            "shutter_type",
            sa.String(10),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.create_check_constraint(
        "chk_camera_shutter",
        "cameras",
        "shutter_type IN ('rolling', 'global', 'unknown')",
    )
    # model_overrides: Phase 3 addition — may be absent from older test DBs
    op.add_column(
        "cameras",
        sa.Column("model_overrides", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_constraint("chk_camera_shutter", "cameras", type_="check")
    op.drop_column("cameras", "shutter_type")
    op.drop_column("cameras", "model_overrides")
```

- [ ] **Step 5: Apply the migration**

```
alembic upgrade head
```

Expected: `Running upgrade <prev> -> <rev>, camera_shutter_and_overrides`

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/test_db_models_cameras.py -v
```

Expected: 5 passed

- [ ] **Step 7: Commit**

```
git add vms/db/models.py alembic/versions/ tests/test_db_models_cameras.py
git commit -m "feat(db): add shutter_type and model_overrides columns to cameras"
```

---

## Task 2: `require_role` dependency helper

**Files:**
- Modify: `vms/api/deps.py`
- Modify: `tests/test_api_deps.py`

- [ ] **Step 1: Write the failing test**

Open `tests/test_api_deps.py` and add at the end:

```python
def test_require_role_raises_403_for_wrong_role() -> None:
    from fastapi import HTTPException

    from vms.api.deps import require_role

    checker = require_role("super_admin")
    with pytest.raises(HTTPException) as exc:
        checker(user={"sub": "1", "role": "admin"})
    assert exc.value.status_code == 403


def test_require_role_passes_for_correct_role() -> None:
    from vms.api.deps import require_role

    checker = require_role("admin", "super_admin")
    result = checker(user={"sub": "1", "role": "admin"})
    assert result["role"] == "admin"


def test_require_role_passes_for_any_listed_role() -> None:
    from vms.api.deps import require_role

    checker = require_role("admin", "super_admin")
    result = checker(user={"sub": "2", "role": "super_admin"})
    assert result["role"] == "super_admin"
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_api_deps.py::test_require_role_raises_403_for_wrong_role -v
```

Expected: FAIL — `ImportError: cannot import name 'require_role'`

- [ ] **Step 3: Add `require_role` to deps.py**

Add at the end of `vms/api/deps.py` (after the existing `get_current_user`):

```python
from collections.abc import Callable


def require_role(*roles: str) -> Callable[..., dict[str, Any]]:
    """Dependency factory — raises 403 if the JWT role is not in *roles*."""

    def _check(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:  # noqa: B008
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _check
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_api_deps.py -v
```

Expected: all pass (new 3 + existing)

- [ ] **Step 5: Commit**

```
git add vms/api/deps.py tests/test_api_deps.py
git commit -m "feat(api): add require_role dependency factory"
```

---

## Task 3: Camera schemas

**Files:**
- Modify: `vms/api/schemas.py`
- Tests will be covered by endpoint tests in Task 5.

- [ ] **Step 1: Add camera schemas to `vms/api/schemas.py`**

Append after the existing `SnapshotResponse` class:

```python
# ---------------------------------------------------------------------------
# Camera schemas
# ---------------------------------------------------------------------------

class CameraResponse(BaseModel):
    camera_id: int
    name: str
    rtsp_url: str
    is_active: bool
    capability_tier: str
    shutter_type: str
    profile_data: str | None
    profiled_at: datetime | None
    model_overrides: str | None
    worker_group: int | None

    model_config = {"from_attributes": True}


class CameraCreate(BaseModel):
    name: str = Field(..., max_length=200)
    rtsp_url: str = Field(..., max_length=500)
    is_active: bool = True
    capability_tier: str = Field(default="FULL", pattern="^(FULL|MID|LOW)$")


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    rtsp_url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class CameraHardwareUpdate(BaseModel):
    shutter_type: str = Field(..., pattern="^(rolling|global|unknown)$")
    capability_tier: str | None = Field(default=None, pattern="^(FULL|MID|LOW)$")


class CameraOverridesUpdate(BaseModel):
    models: dict[str, str | None] | None = None
    thresholds: dict[str, float] | None = None


class ResolvedSettingItem(BaseModel):
    value: Any
    source: str


class ResolvedConfigResponse(BaseModel):
    camera_id: int
    settings: dict[str, ResolvedSettingItem]
```

- [ ] **Step 2: Verify import works**

```
python -c "from vms.api.schemas import CameraResponse, CameraCreate, CameraHardwareUpdate, CameraOverridesUpdate, ResolvedConfigResponse; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```
git add vms/api/schemas.py
git commit -m "feat(api): add camera request/response schemas"
```

---

## Task 4: ShutterProfile config resolver

**Files:**
- Create: `vms/inference/shutter_profile.py`
- Create: `tests/test_inference_shutter_profile.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_inference_shutter_profile.py`:

```python
"""Tests for ShutterProfile config resolver."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from vms.config import Settings


def _settings(**kwargs) -> Settings:  # type: ignore[no-untyped-def]
    defaults = {
        "db_url": "postgresql://vms:vms@localhost:5434/vms_test",
        "redis_url": "redis://localhost:6379/0",
        "jwt_secret": "test",
        "scrfd_model": "models/scrfd.onnx",
        "adaface_model": "models/adaface.onnx",
        "bytetrack_config": "bytetrack.yaml",
    }
    defaults.update(kwargs)
    return Settings(**defaults)


def test_rolling_lowers_adaface_min_sim() -> None:
    from vms.inference.shutter_profile import resolve_camera_config

    s = _settings(adaface_min_sim=0.72)
    result = resolve_camera_config(1, "rolling", None, s)
    assert result["adaface_min_sim"]["value"] == pytest.approx(0.62)
    assert result["adaface_min_sim"]["source"] == "shutter:rolling"


def test_rolling_lowers_scrfd_conf() -> None:
    from vms.inference.shutter_profile import resolve_camera_config

    s = _settings(scrfd_conf=0.60)
    result = resolve_camera_config(1, "rolling", None, s)
    assert result["scrfd_conf"]["value"] == pytest.approx(0.50)
    assert result["scrfd_conf"]["source"] == "shutter:rolling"


def test_rolling_sets_burst_frames_to_five() -> None:
    from vms.inference.shutter_profile import resolve_camera_config

    result = resolve_camera_config(1, "rolling", None, _settings())
    assert result["burst_frames"]["value"] == 5
    assert result["burst_frames"]["source"] == "shutter:rolling"


def test_rolling_raises_body_weight() -> None:
    from vms.inference.shutter_profile import resolve_camera_config

    result = resolve_camera_config(1, "rolling", None, _settings())
    assert result["body_weight_multiplier"]["value"] == pytest.approx(1.2)
    assert result["body_weight_multiplier"]["source"] == "shutter:rolling"


def test_global_uses_defaults() -> None:
    from vms.inference.shutter_profile import resolve_camera_config

    s = _settings(adaface_min_sim=0.72, scrfd_conf=0.60)
    result = resolve_camera_config(1, "global", None, s)
    assert result["adaface_min_sim"]["value"] == pytest.approx(0.72)
    assert result["adaface_min_sim"]["source"] == "global_default"
    assert result["burst_frames"]["value"] == 1
    assert result["burst_frames"]["source"] == "global_default"
    assert result["body_weight_multiplier"]["value"] == pytest.approx(1.0)
    assert result["body_weight_multiplier"]["source"] == "global_default"


def test_unknown_treated_as_rolling() -> None:
    from vms.inference.shutter_profile import resolve_camera_config

    s = _settings(adaface_min_sim=0.72)
    result = resolve_camera_config(1, "unknown", None, s)
    assert result["adaface_min_sim"]["value"] == pytest.approx(0.62)
    assert result["adaface_min_sim"]["source"] == "shutter:rolling"


def test_manual_override_beats_shutter_adjustment() -> None:
    from vms.inference.shutter_profile import resolve_camera_config

    import json

    overrides = json.dumps({"thresholds": {"adaface_min_sim": 0.90}})
    s = _settings(adaface_min_sim=0.72)
    result = resolve_camera_config(1, "rolling", overrides, s)
    assert result["adaface_min_sim"]["value"] == pytest.approx(0.90)
    assert result["adaface_min_sim"]["source"] == "manual_override"


def test_model_override_sets_face_embedder() -> None:
    from vms.inference.shutter_profile import resolve_camera_config

    import json

    overrides = json.dumps({"models": {"face_embedder": "adaface_ir50_acme_v2"}})
    result = resolve_camera_config(1, "global", overrides, _settings())
    assert result["face_embedder"]["value"] == "adaface_ir50_acme_v2"
    assert result["face_embedder"]["source"] == "manual_override"


def test_no_model_override_returns_global_default() -> None:
    from vms.inference.shutter_profile import resolve_camera_config

    result = resolve_camera_config(1, "global", None, _settings())
    assert result["face_embedder"]["source"] == "global_default"
    assert result["violence_model"]["source"] == "global_default"


def test_malformed_model_overrides_json_falls_back_to_defaults() -> None:
    from vms.inference.shutter_profile import resolve_camera_config

    result = resolve_camera_config(1, "global", "not-valid-json{{{", _settings())
    assert result["adaface_min_sim"]["source"] == "global_default"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_inference_shutter_profile.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'vms.inference.shutter_profile'`

- [ ] **Step 3: Create `vms/inference/shutter_profile.py`**

```python
"""ShutterProfile — pipeline threshold adjustments per camera shutter type.

Resolution hierarchy (first match wins):
1. Per-camera manual override  (model_overrides JSON thresholds/models)
2. Shutter-type adjustment     (rolling: -0.10 on face thresholds, burst=5, body×1.2)
3. Hard-coded defaults         (from Settings)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from vms.config import Settings, get_settings


@dataclass(frozen=True)
class ShutterAdjustment:
    adaface_min_sim_delta: float
    scrfd_conf_delta: float
    burst_frames: int
    body_weight_multiplier: float


_ROLLING = ShutterAdjustment(
    adaface_min_sim_delta=-0.10,
    scrfd_conf_delta=-0.10,
    burst_frames=5,
    body_weight_multiplier=1.2,
)

_GLOBAL = ShutterAdjustment(
    adaface_min_sim_delta=0.0,
    scrfd_conf_delta=0.0,
    burst_frames=1,
    body_weight_multiplier=1.0,
)

# 'unknown' conservative fallback — same as rolling
_ADJUSTMENTS: dict[str, ShutterAdjustment] = {
    "rolling": _ROLLING,
    "global": _GLOBAL,
    "unknown": _ROLLING,
}

_SHUTTER_SOURCE: dict[str, str] = {
    "rolling": "shutter:rolling",
    "global": "shutter:global",
    "unknown": "shutter:rolling",  # reported as rolling since that's the applied profile
}


def resolve_camera_config(
    camera_id: int,
    shutter_type: str,
    model_overrides_json: str | None,
    settings: Settings | None = None,
) -> dict[str, dict[str, Any]]:
    """Return resolved config for one camera with source labels.

    Each entry: ``{"value": <resolved_value>, "source": <source_label>}``
    Source labels: ``"manual_override"`` | ``"shutter:rolling"`` | ``"shutter:global"``
                   | ``"global_default"``
    """
    if settings is None:
        settings = get_settings()

    adj = _ADJUSTMENTS.get(shutter_type, _ROLLING)
    shutter_src = _SHUTTER_SOURCE.get(shutter_type, "shutter:rolling")

    overrides: dict[str, Any] = {}
    if model_overrides_json:
        try:
            parsed = json.loads(model_overrides_json)
            if isinstance(parsed, dict):
                overrides = parsed
        except (json.JSONDecodeError, ValueError):
            pass

    t_overrides: dict[str, float] = overrides.get("thresholds") or {}
    m_overrides: dict[str, str | None] = overrides.get("models") or {}

    def _threshold(key: str, base: float, delta: float) -> dict[str, Any]:
        if key in t_overrides:
            return {"value": t_overrides[key], "source": "manual_override"}
        if delta != 0.0:
            return {"value": round(base + delta, 4), "source": shutter_src}
        return {"value": base, "source": "global_default"}

    def _model(key: str, default: str) -> dict[str, Any]:
        val = m_overrides.get(key)
        if val is not None:
            return {"value": val, "source": "manual_override"}
        return {"value": default, "source": "global_default"}

    def _burst() -> dict[str, Any]:
        if "burst_frames" in t_overrides:
            return {"value": int(t_overrides["burst_frames"]), "source": "manual_override"}
        if adj.burst_frames != 1:
            return {"value": adj.burst_frames, "source": shutter_src}
        return {"value": 1, "source": "global_default"}

    def _body_weight() -> dict[str, Any]:
        if adj.body_weight_multiplier != 1.0:
            return {"value": adj.body_weight_multiplier, "source": shutter_src}
        return {"value": 1.0, "source": "global_default"}

    return {
        "adaface_min_sim": _threshold(
            "adaface_min_sim", settings.adaface_min_sim, adj.adaface_min_sim_delta
        ),
        "scrfd_conf": _threshold(
            "scrfd_conf", settings.scrfd_conf, adj.scrfd_conf_delta
        ),
        "burst_frames": _burst(),
        "body_weight_multiplier": _body_weight(),
        "face_embedder": _model("face_embedder", "adaface_ir50"),
        "violence_model": _model("violence", "movinet_a2"),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_inference_shutter_profile.py -v
```

Expected: 10 passed

- [ ] **Step 5: Commit**

```
git add vms/inference/shutter_profile.py tests/test_inference_shutter_profile.py
git commit -m "feat(inference): add ShutterProfile config resolver"
```

---

## Task 5: Camera CRUD endpoints

**Files:**
- Create: `vms/api/routes/cameras.py`
- Modify: `vms/api/main.py`
- Create: `tests/test_api_cameras.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_cameras.py`:

```python
"""Tests for /api/cameras CRUD endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.main import app
from vms.db.models import Camera


def _auth(role: str = "admin") -> dict[str, str]:
    from vms.api.deps import create_access_token
    return {"Authorization": f"Bearer {create_access_token(99, role)}"}


def _utc_naive():  # type: ignore[no-untyped-def]
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# GET /api/cameras
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_cameras_returns_all(db_session: Session) -> None:
    from vms.api.deps import get_db

    db_session.add(Camera(name="Cam A", rtsp_url="rtsp://a", capability_tier="FULL"))
    db_session.add(Camera(name="Cam B", rtsp_url="rtsp://b", capability_tier="MID"))
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/cameras", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    names = [cam["name"] for cam in r.json()]
    assert "Cam A" in names
    assert "Cam B" in names


@pytest.mark.asyncio
async def test_list_cameras_requires_auth() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/cameras")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/cameras
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_camera_returns_201(db_session: Session) -> None:
    from vms.api.deps import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/cameras",
                json={"name": "Gate 1", "rtsp_url": "rtsp://gate1", "capability_tier": "FULL"},
                headers=_auth(),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Gate 1"
    assert body["shutter_type"] == "unknown"
    assert body["capability_tier"] == "FULL"


@pytest.mark.asyncio
async def test_create_camera_rejects_invalid_tier(db_session: Session) -> None:
    from vms.api.deps import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/cameras",
                json={"name": "X", "rtsp_url": "rtsp://x", "capability_tier": "ULTRA"},
                headers=_auth(),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/cameras/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_camera_returns_detail(db_session: Session) -> None:
    from vms.api.deps import get_db

    cam = Camera(name="Floor 3", rtsp_url="rtsp://f3", capability_tier="FULL", shutter_type="global")
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/cameras/{cam.camera_id}", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert r.json()["shutter_type"] == "global"


@pytest.mark.asyncio
async def test_get_camera_404_for_missing(db_session: Session) -> None:
    from vms.api.deps import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/cameras/99999", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/cameras/{id}
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_camera_updates_name(db_session: Session) -> None:
    from vms.api.deps import get_db

    cam = Camera(name="Old Name", rtsp_url="rtsp://x", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(
                f"/api/cameras/{cam.camera_id}",
                json={"name": "New Name"},
                headers=_auth(),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_api_cameras.py -v
```

Expected: FAIL — `404` responses (routes don't exist yet)

- [ ] **Step 3: Create `vms/api/routes/cameras.py` with CRUD endpoints**

```python
"""Camera CRUD and configuration endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from vms.api.deps import get_current_user, get_db, require_role
from vms.api.schemas import CameraCreate, CameraResponse, CameraUpdate
from vms.db.models import Camera

router = APIRouter()


def _get_camera_or_404(camera_id: int, db: Session) -> Camera:
    cam = db.query(Camera).filter(Camera.camera_id == camera_id).first()
    if cam is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return cam


@router.get("/cameras", response_model=list[CameraResponse])
def list_cameras(
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[Camera]:
    return db.query(Camera).order_by(Camera.camera_id).all()


@router.post("/cameras", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
def create_camera(
    body: CameraCreate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Camera:
    cam = Camera(
        name=body.name,
        rtsp_url=body.rtsp_url,
        is_active=body.is_active,
        capability_tier=body.capability_tier,
    )
    db.add(cam)
    db.commit()
    db.refresh(cam)
    return cam


@router.get("/cameras/{camera_id}", response_model=CameraResponse)
def get_camera(
    camera_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Camera:
    return _get_camera_or_404(camera_id, db)


@router.patch("/cameras/{camera_id}", response_model=CameraResponse)
def update_camera(
    camera_id: int,
    body: CameraUpdate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Camera:
    cam = _get_camera_or_404(camera_id, db)
    if body.name is not None:
        cam.name = body.name
    if body.rtsp_url is not None:
        cam.rtsp_url = body.rtsp_url
    if body.is_active is not None:
        cam.is_active = body.is_active
    db.commit()
    db.refresh(cam)
    return cam
```

- [ ] **Step 4: Register the router in `vms/api/main.py`**

Add the import and include_router call:

```python
from vms.api.routes import alerts, anomaly_detectors, auth, cameras, health, maintenance, persons, state

# ... (existing includes) ...
app.include_router(cameras.router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_api_cameras.py -v
```

Expected: 9 passed

- [ ] **Step 6: Commit**

```
git add vms/api/routes/cameras.py vms/api/main.py tests/test_api_cameras.py
git commit -m "feat(api): add camera CRUD endpoints"
```

---

## Task 6: Hardware and Overrides endpoints

**Files:**
- Modify: `vms/api/routes/cameras.py`
- Modify: `tests/test_api_cameras.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_cameras.py`:

```python
# ---------------------------------------------------------------------------
# PATCH /api/cameras/{id}/hardware
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_hardware_requires_super_admin(db_session: Session) -> None:
    from vms.api.deps import get_db

    cam = Camera(name="H1", rtsp_url="rtsp://h1", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(
                f"/api/cameras/{cam.camera_id}/hardware",
                json={"shutter_type": "global"},
                headers=_auth("admin"),  # admin — should be rejected
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_patch_hardware_super_admin_updates_shutter_type(db_session: Session) -> None:
    from vms.api.deps import get_db

    cam = Camera(name="H2", rtsp_url="rtsp://h2", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(
                f"/api/cameras/{cam.camera_id}/hardware",
                json={"shutter_type": "rolling"},
                headers=_auth("super_admin"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert r.json()["shutter_type"] == "rolling"


@pytest.mark.asyncio
async def test_patch_hardware_rejects_invalid_shutter_type(db_session: Session) -> None:
    from vms.api.deps import get_db

    cam = Camera(name="H3", rtsp_url="rtsp://h3", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(
                f"/api/cameras/{cam.camera_id}/hardware",
                json={"shutter_type": "ccd"},
                headers=_auth("super_admin"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /api/cameras/{id}/overrides
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patch_overrides_saves_model_overrides_json(db_session: Session) -> None:
    from vms.api.deps import get_db
    import json

    cam = Camera(name="O1", rtsp_url="rtsp://o1", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(
                f"/api/cameras/{cam.camera_id}/overrides",
                json={"thresholds": {"adaface_min_sim": 0.85}, "models": {}},
                headers=_auth("admin"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    saved = json.loads(r.json()["model_overrides"])
    assert saved["thresholds"]["adaface_min_sim"] == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_patch_overrides_admin_allowed(db_session: Session) -> None:
    from vms.api.deps import get_db

    cam = Camera(name="O2", rtsp_url="rtsp://o2", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.patch(
                f"/api/cameras/{cam.camera_id}/overrides",
                json={"thresholds": {}, "models": {}},
                headers=_auth("admin"),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_api_cameras.py::test_patch_hardware_requires_super_admin tests/test_api_cameras.py::test_patch_overrides_saves_model_overrides_json -v
```

Expected: FAIL — `404` (endpoints don't exist yet)

- [ ] **Step 3: Add hardware + overrides endpoints to `vms/api/routes/cameras.py`**

Add these imports at the top of `vms/api/routes/cameras.py`:

```python
import json
from datetime import datetime, timezone

import redis.asyncio as aioredis

from vms.api.deps import get_api_redis
from vms.api.schemas import CameraHardwareUpdate, CameraOverridesUpdate
from vms.db.audit import write_audit_event
```

Then append the two endpoints:

```python
@router.patch("/cameras/{camera_id}/hardware", response_model=CameraResponse)
async def update_camera_hardware(
    camera_id: int,
    body: CameraHardwareUpdate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(require_role("super_admin")),  # noqa: B008
    redis: aioredis.Redis = Depends(get_api_redis),  # noqa: B008
) -> Camera:
    cam = _get_camera_or_404(camera_id, db)
    old_shutter = cam.shutter_type
    old_tier = cam.capability_tier
    cam.shutter_type = body.shutter_type
    if body.capability_tier is not None:
        cam.capability_tier = body.capability_tier
    db.commit()
    db.refresh(cam)
    write_audit_event(
        db,
        event_type="CAMERA_HARDWARE_UPDATED",
        actor_id=int(_user["sub"]),
        payload={
            "camera_id": camera_id,
            "from": {"shutter_type": old_shutter, "capability_tier": old_tier},
            "to": {"shutter_type": cam.shutter_type, "capability_tier": cam.capability_tier},
        },
    )
    await redis.publish(f"camera_config_changed:{camera_id}", "hardware")
    return cam


@router.patch("/cameras/{camera_id}/overrides", response_model=CameraResponse)
async def update_camera_overrides(
    camera_id: int,
    body: CameraOverridesUpdate,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
    redis: aioredis.Redis = Depends(get_api_redis),  # noqa: B008
) -> Camera:
    cam = _get_camera_or_404(camera_id, db)
    old_overrides = cam.model_overrides
    cam.model_overrides = json.dumps(
        {
            "models": body.models or {},
            "thresholds": body.thresholds or {},
        }
    )
    db.commit()
    db.refresh(cam)
    write_audit_event(
        db,
        event_type="CAMERA_OVERRIDES_UPDATED",
        actor_id=int(_user["sub"]),
        payload={
            "camera_id": camera_id,
            "from": old_overrides,
            "to": cam.model_overrides,
        },
    )
    await redis.publish(f"camera_config_changed:{camera_id}", "overrides")
    return cam
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_api_cameras.py -v
```

Expected: all pass (17 tests)

- [ ] **Step 5: Commit**

```
git add vms/api/routes/cameras.py tests/test_api_cameras.py
git commit -m "feat(api): add camera hardware and overrides PATCH endpoints"
```

---

## Task 7: Resolved-config endpoint

**Files:**
- Modify: `vms/api/routes/cameras.py`
- Modify: `tests/test_api_cameras.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api_cameras.py`:

```python
# ---------------------------------------------------------------------------
# GET /api/cameras/{id}/resolved-config
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolved_config_rolling_returns_shutter_adjusted_values(
    db_session: Session,
) -> None:
    from vms.api.deps import get_db

    cam = Camera(
        name="RC1", rtsp_url="rtsp://rc1", capability_tier="FULL", shutter_type="rolling"
    )
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/cameras/{cam.camera_id}/resolved-config", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    settings = r.json()["settings"]
    assert settings["adaface_min_sim"]["source"] == "shutter:rolling"
    assert settings["burst_frames"]["value"] == 5


@pytest.mark.asyncio
async def test_resolved_config_global_returns_default_values(db_session: Session) -> None:
    from vms.api.deps import get_db

    cam = Camera(
        name="RC2", rtsp_url="rtsp://rc2", capability_tier="FULL", shutter_type="global"
    )
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/cameras/{cam.camera_id}/resolved-config", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    settings = r.json()["settings"]
    assert settings["adaface_min_sim"]["source"] == "global_default"
    assert settings["burst_frames"]["value"] == 1


@pytest.mark.asyncio
async def test_resolved_config_manual_override_wins_over_shutter(
    db_session: Session,
) -> None:
    import json as _json
    from vms.api.deps import get_db

    overrides = _json.dumps({"thresholds": {"adaface_min_sim": 0.95}, "models": {}})
    cam = Camera(
        name="RC3",
        rtsp_url="rtsp://rc3",
        capability_tier="FULL",
        shutter_type="rolling",
        model_overrides=overrides,
    )
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/cameras/{cam.camera_id}/resolved-config", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert r.json()["settings"]["adaface_min_sim"]["source"] == "manual_override"
    assert r.json()["settings"]["adaface_min_sim"]["value"] == pytest.approx(0.95)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_api_cameras.py::test_resolved_config_rolling_returns_shutter_adjusted_values -v
```

Expected: FAIL — `404`

- [ ] **Step 3: Add resolved-config endpoint to `vms/api/routes/cameras.py`**

Add import at top:

```python
from vms.api.schemas import ResolvedConfigResponse, ResolvedSettingItem
from vms.inference.shutter_profile import resolve_camera_config
```

Append endpoint:

```python
@router.get("/cameras/{camera_id}/resolved-config", response_model=ResolvedConfigResponse)
def get_resolved_config(
    camera_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> ResolvedConfigResponse:
    cam = _get_camera_or_404(camera_id, db)
    raw = resolve_camera_config(
        camera_id=cam.camera_id,
        shutter_type=cam.shutter_type,
        model_overrides_json=cam.model_overrides,
    )
    return ResolvedConfigResponse(
        camera_id=camera_id,
        settings={k: ResolvedSettingItem(**v) for k, v in raw.items()},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_api_cameras.py -v
```

Expected: all 20 pass

- [ ] **Step 5: Commit**

```
git add vms/api/routes/cameras.py tests/test_api_cameras.py
git commit -m "feat(api): add resolved-config endpoint"
```

---

## Task 8: Profile endpoints (stub)

The full CameraProfiler (motion-skew shutter detection) is a separate Phase 3 plan. This task delivers the API surface — `POST /profile` accepts a body with profiler results and `GET /profile` returns them — so the frontend Hardware tab can call these endpoints now.

**Files:**
- Modify: `vms/api/routes/cameras.py`
- Modify: `vms/api/schemas.py`
- Modify: `tests/test_api_cameras.py`

- [ ] **Step 1: Add `ProfileData` and `ProfileResponse` schemas to `vms/api/schemas.py`**

Append after `ResolvedConfigResponse`:

```python
class ProfileData(BaseModel):
    resolution_w: int | None = None
    resolution_h: int | None = None
    fps_measured: float | None = None
    focus_score: float | None = None
    shutter_suggestion: str | None = Field(
        default=None, pattern="^(rolling|global|unknown)$"
    )
    shutter_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    suggested_tier: str | None = Field(default=None, pattern="^(FULL|MID|LOW)$")


class ProfileResponse(BaseModel):
    camera_id: int
    profile_data: ProfileData | None
    profiled_at: datetime | None
    capability_tier: str
    shutter_type: str

    model_config = {"from_attributes": False}
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_api_cameras.py`:

```python
# ---------------------------------------------------------------------------
# POST /api/cameras/{id}/profile  and  GET /api/cameras/{id}/profile
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_profile_stores_data_and_returns_202(db_session: Session) -> None:
    from vms.api.deps import get_db

    cam = Camera(name="P1", rtsp_url="rtsp://p1", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                f"/api/cameras/{cam.camera_id}/profile",
                json={
                    "resolution_w": 1920,
                    "resolution_h": 1080,
                    "fps_measured": 15.0,
                    "focus_score": 42.0,
                    "shutter_suggestion": "rolling",
                    "shutter_confidence": 0.87,
                    "suggested_tier": "FULL",
                },
                headers=_auth(),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 202


@pytest.mark.asyncio
async def test_get_profile_returns_last_profile_data(db_session: Session) -> None:
    import json as _json
    from vms.api.deps import get_db

    profile = {
        "resolution_w": 1280, "resolution_h": 720,
        "fps_measured": 10.0, "focus_score": 28.0,
        "shutter_suggestion": "rolling", "shutter_confidence": 0.75,
        "suggested_tier": "MID",
    }
    cam = Camera(
        name="P2",
        rtsp_url="rtsp://p2",
        capability_tier="FULL",
        profile_data=_json.dumps(profile),
    )
    db_session.add(cam)
    db_session.flush()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get(f"/api/cameras/{cam.camera_id}/profile", headers=_auth())
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    body = r.json()
    assert body["profile_data"]["fps_measured"] == pytest.approx(10.0)
    assert body["profile_data"]["shutter_suggestion"] == "rolling"
```

- [ ] **Step 3: Run tests to verify they fail**

```
pytest tests/test_api_cameras.py::test_post_profile_stores_data_and_returns_202 -v
```

Expected: FAIL — `404`

- [ ] **Step 4: Add profile endpoints to `vms/api/routes/cameras.py`**

Add imports:

```python
from vms.api.schemas import ProfileData, ProfileResponse
```

Append endpoints:

```python
@router.post("/cameras/{camera_id}/profile", status_code=status.HTTP_202_ACCEPTED)
def submit_profile(
    camera_id: int,
    body: ProfileData,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> dict[str, str]:
    cam = _get_camera_or_404(camera_id, db)
    cam.profile_data = json.dumps(body.model_dump(exclude_none=False))
    cam.profiled_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"status": "accepted"}


@router.get("/cameras/{camera_id}/profile", response_model=ProfileResponse)
def get_profile(
    camera_id: int,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> ProfileResponse:
    cam = _get_camera_or_404(camera_id, db)
    profile_data: ProfileData | None = None
    if cam.profile_data:
        try:
            profile_data = ProfileData(**json.loads(cam.profile_data))
        except (json.JSONDecodeError, ValueError):
            profile_data = None
    return ProfileResponse(
        camera_id=cam.camera_id,
        profile_data=profile_data,
        profiled_at=cam.profiled_at,
        capability_tier=cam.capability_tier,
        shutter_type=cam.shutter_type,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_api_cameras.py -v
```

Expected: all 24 pass

- [ ] **Step 6: Commit**

```
git add vms/api/routes/cameras.py vms/api/schemas.py tests/test_api_cameras.py
git commit -m "feat(api): add camera profile submit and get endpoints"
```

---

## Task 9: Full suite verification

- [ ] **Step 1: Run lint and type-check**

```
ruff check vms/ tests/
black vms/ tests/
mypy vms/
```

Expected: no errors. Fix any that appear before continuing.

- [ ] **Step 2: Run the full test suite**

```
pytest --tb=short -q
```

Expected: 405+ passed (prior count), 5 deselected (heavy_models). New camera tests add ~24 tests, shutter_profile adds ~10 = approximately 439+ passed.

- [ ] **Step 3: Verify coverage on new modules**

```
pytest --cov=vms/api/routes/cameras --cov=vms/inference/shutter_profile --cov-report=term-missing -q
```

Expected: ≥80% coverage on both modules.

- [ ] **Step 4: Final commit if any lint fixes were made**

```
git add -u
git commit -m "chore: lint and type fixes for camera config API"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ §B DB additions — shutter_type + CHECK constraint (Task 1)
- ✅ §B API — all 8 endpoints including resolved-config + profile (Tasks 5–8)
- ✅ §L.3 model_overrides migration (Task 1) + PATCH /overrides endpoint (Task 6)
- ✅ §L.3.1 ShutterProfile resolver (Task 4) with correct 5-level hierarchy
- ✅ §L.4 hierarchy respected in resolve_camera_config (manual → shutter → default)
- ✅ §J API delta — all new camera endpoints listed
- ✅ Audit log writes on hardware + overrides PATCH (Task 6)
- ✅ Redis `camera_config_changed` publish (Task 6)
- ✅ Role gating: hardware = super_admin, all others = any authenticated user (Tasks 2, 6)
- ✅ `require_role` dependency (Task 2)
- ⚠️ Frontend `<CameraDetail />` — **Phase 4, out of scope for this plan**
- ⚠️ Full CameraProfiler motion-skew detection — **separate Phase 3 plan**; profile endpoint here is a stub that accepts operator-supplied profile data
