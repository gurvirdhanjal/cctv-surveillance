# Phase 2a Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE**

**Goal:** Close all critical/high/medium gaps found in the post-Phase-2a audit before starting the anomaly framework, so Phase 2b is built on a correct, production-hardened foundation.

**Architecture:** 12 sequential tasks covering security (JWT expiry, login endpoint, role checks), integration (IdentityEngine wired into DBWriter, faiss_dirty events from API, face-to-track association), and production robustness (audit race fix, zone caching, registry eviction, graceful JSON error handling). All changes follow the project's TDD pattern. No new tables, no migration required.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, PostgreSQL + pgvector, Redis Streams, FAISS, passlib[bcrypt], python-jose, pytest-asyncio, fakeredis.

**Spec refs:**
- `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` §H (auth, GDPR), §E (faiss_dirty)
- `docs/superpowers/specs/2026-05-01-vms-db-edge-cases.md` §3 (audit chain), §14 (login audit)

---

## Context

After completing Phase 2a (Identity Framework, 128 tests), an audit revealed the following gaps that block Phase 2b:

**Critical:** JWT tokens never expire (no `exp` claim); no login endpoint exists; `DBWriter` generates random `global_track_id` per flush instead of calling `IdentityEngine`; `faiss_dirty` events are never published after enrollment or purge — FAISS is always stale.

**High:** `IdentityEngine._registry` grows unbounded (no eviction); `ZonePresenceTracker` queries all zones on every frame (DB perf); audit hash-chain has a race condition under concurrent writers; malformed homography JSON propagates uncaught.

**Medium:** `create_person`/`add_embedding` allow guard-role users; purged persons appear in search; `_STALE_MS` hardcoded; `ZonePresenceTracker` holds a long-lived session.

---

## Files Modified / Created

| Action | Path |
|---|---|
| Modify | `CLAUDE.md` |
| Modify | `requirements.txt` |
| Modify | `vms/config.py` |
| Modify | `vms/api/deps.py` |
| Modify | `vms/api/main.py` |
| Modify | `vms/api/schemas.py` |
| Create | `vms/api/routes/auth.py` |
| Modify | `vms/api/routes/persons.py` |
| Modify | `vms/db/audit.py` |
| Modify | `vms/identity/engine.py` |
| Modify | `vms/identity/homography.py` |
| Modify | `vms/identity/zone_presence.py` |
| Modify | `vms/inference/messages.py` |
| Modify | `vms/inference/engine.py` |
| Modify | `vms/writer/db_writer.py` |
| Modify | `tests/test_api_persons.py` |
| Create | `tests/test_api_auth.py` |
| Modify | `tests/test_db_audit.py` |
| Modify | `tests/test_identity_engine.py` |
| Modify | `tests/test_identity_zone_presence.py` |
| Modify | `tests/test_inference_messages.py` |
| Modify | `tests/test_inference_engine.py` |
| Modify | `tests/test_db_writer.py` |

---

## Task 1: Update CLAUDE.md (IST timezone + phase status)

**Files:**
- Modify: `CLAUDE.md`

- [x] **Step 1: Update §3 (Current phase)**

In `CLAUDE.md`, replace the current phase block (lines starting with `## 3. Current phase`) with:

```markdown
## 3. Current phase

We are at **Phase 2b: Anomaly Framework** (not yet started — plan not written).

**Phase 2a Hardening** is **COMPLETE** — 159 tests passing as of commit `019e45e`. Plan: `docs/superpowers/plans/2026-05-14-vms-v2-phase2a-hardening.md`.

**Phase 2a** (Identity Framework) is **COMPLETE** — 128 tests passing as of commit `634c8c4`. Plan: `docs/superpowers/plans/2026-05-14-vms-v2-phase2a-identity-framework.md`. Notes: `docs/superpowers/notes/2026-05-14-vms-v2-phase2a-implementation-notes.md`.

**Phase 1B** (Ingestion, Inference, and Base API) is **COMPLETE** — 96 tests passing as of commit `019e45e`. Plan: `docs/superpowers/plans/2026-05-09-vms-v2-phase1b-ingestion-inference-api.md`. Notes: `docs/superpowers/notes/2026-05-09-vms-v2-phase1b-implementation-notes.md`.

**Phase 1A** (Database Schema, Project Scaffold, and Config) is **COMPLETE** — 57 tests passing as of commit `4a4bc49`. Plan: `docs/superpowers/plans/2026-05-01-vms-v2-phase1a-db-schema.md`.

Subsequent phases (Phase 2b Anomaly Framework, Phase 3 Profiler + Dispatcher + Audit, Phase 4 Frontend, Phase 5 Forensic + Hardening, Phase 6 Camera Rollout) each get their own plan file when started. **Do not start a phase before its plan exists and is approved.**
```

- [x] **Step 2: Add timezone note to §5 (Coding standards)**

After the line about `datetime.utcnow()` in §12 (Common pitfalls), add a row:

```markdown
| Using `datetime.utcnow()` without awareness | All DB timestamps are UTC-naive (`TIMESTAMP WITHOUT TIME ZONE`). Use `datetime.now(timezone.utc).replace(tzinfo=None)`. Developer timezone is **IST (UTC+5:30)**; notes/plans use IST wall-clock dates but all code and DB use UTC |
```

Also add near the top of §5 Coding standards:

```markdown
- **Timezone convention:** DB stores all timestamps as UTC-naive (`TIMESTAMP WITHOUT TIME ZONE`). In code, always use `datetime.now(timezone.utc).replace(tzinfo=None)` — never bare `datetime.utcnow()`. Developer timezone is **IST (UTC+5:30)** for notes and plan dates; this does not affect DB or API behaviour.
```

- [x] **Step 3: Commit**

```
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md — phase 2a hardening status, IST timezone note"
```

---

## Task 2: Add configurable settings for identity + zone cache

**Files:**
- Modify: `vms/config.py`
- Modify: `tests/test_config.py`

- [x] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_reid_stale_ms_default() -> None:
    s = Settings(db_url="postgresql://x/y", jwt_secret="s")  # type: ignore[call-arg]
    assert s.reid_stale_ms == 300_000

def test_zone_cache_ttl_s_default() -> None:
    s = Settings(db_url="postgresql://x/y", jwt_secret="s")  # type: ignore[call-arg]
    assert s.zone_cache_ttl_s == 30
```

- [x] **Step 2: Run tests to verify they fail**

```
pytest tests/test_config.py::test_reid_stale_ms_default tests/test_config.py::test_zone_cache_ttl_s_default -v
```
Expected: FAIL — `Settings` has no field `reid_stale_ms` or `zone_cache_ttl_s`.

- [x] **Step 3: Add fields to Settings**

In `vms/config.py`, add after the `min_face_px` line:

```python
    # identity
    reid_stale_ms: int = 300_000  # 5 min; how long before a tracklet is considered stale
    zone_cache_ttl_s: int = 30    # seconds between zone polygon reloads
```

- [x] **Step 4: Run tests to verify they pass**

```
pytest tests/test_config.py -v
```
Expected: all PASS.

- [x] **Step 5: Commit**

```
git add vms/config.py tests/test_config.py
git commit -m "feat(config): add reid_stale_ms and zone_cache_ttl_s settings"
```

---

## Task 3: Fix JWT expiry — add `exp` claim to tokens

**Files:**
- Modify: `vms/api/deps.py`
- Modify: `tests/test_api_deps.py`

- [x] **Step 1: Write the failing test**

Add to `tests/test_api_deps.py`:

```python
import time
from vms.api.deps import create_access_token, decode_access_token

def test_token_contains_exp_claim() -> None:
    token = create_access_token(user_id=1, role="guard")
    payload = decode_access_token(token)
    assert "exp" in payload
    assert payload["exp"] > int(time.time())

def test_expired_token_raises() -> None:
    from jose import jwt
    from vms.config import get_settings
    settings = get_settings()
    past_payload = {"sub": "1", "role": "guard", "exp": int(time.time()) - 10}
    token = jwt.encode(past_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException) as exc_info:
        from vms.api.deps import get_current_user
        from fastapi.security import HTTPAuthorizationCredentials
        get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert exc_info.value.status_code == 401
```

- [x] **Step 2: Run tests to verify they fail**

```
pytest tests/test_api_deps.py::test_token_contains_exp_claim tests/test_api_deps.py::test_expired_token_raises -v
```
Expected: `test_token_contains_exp_claim` FAIL (no `exp` key).

- [x] **Step 3: Fix `create_access_token` in `vms/api/deps.py`**

Replace the existing `create_access_token` function:

```python
from datetime import datetime, timedelta, timezone

def create_access_token(user_id: int, role: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
    }
    return str(jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm))
```

- [x] **Step 4: Run tests to verify they pass**

```
pytest tests/test_api_deps.py -v
```
Expected: all PASS.

- [x] **Step 5: Commit**

```
git add vms/api/deps.py tests/test_api_deps.py
git commit -m "fix(auth): add exp claim to JWT tokens — tokens now expire after jwt_expire_hours"
```

---

## Task 4: Add login endpoint `POST /api/auth/token`

**Files:**
- Modify: `requirements.txt`
- Modify: `vms/api/deps.py`
- Modify: `vms/api/schemas.py`
- Create: `vms/api/routes/auth.py`
- Modify: `vms/api/main.py`
- Create: `tests/test_api_auth.py`

- [x] **Step 1: Add passlib dependency**

Add to `requirements.txt`:
```
passlib[bcrypt]==1.7.4
```

Install it:
```
pip install passlib[bcrypt]==1.7.4
```

- [x] **Step 2: Add password utilities to `vms/api/deps.py`**

Add after the existing imports in `vms/api/deps.py`:

```python
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return bool(_pwd_context.verify(plain, hashed))


def hash_password(password: str) -> str:
    return str(_pwd_context.hash(password))
```

- [x] **Step 3: Add schemas to `vms/api/schemas.py`**

Add to `vms/api/schemas.py`:

```python
class TokenRequest(BaseModel):
    username: str = Field(..., max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

- [x] **Step 4: Write the failing tests**

Create `tests/test_api_auth.py`:

```python
"""Tests for POST /api/auth/token."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session

from vms.api.deps import hash_password
from vms.api.main import app
from vms.db.models import User


@pytest.mark.asyncio
async def test_login_returns_token(db_session: Session) -> None:
    user = User(
        username="testop",
        password_hash=hash_password("correcthorse"),
        role="guard",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/token",
            json={"username": "testop", "password": "correcthorse"},
        )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(db_session: Session) -> None:
    user = User(
        username="testop2",
        password_hash=hash_password("correcthorse"),
        role="guard",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/token",
            json={"username": "testop2", "password": "wrongpassword"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user_returns_401(db_session: Session) -> None:
    user = User(
        username="inactiveop",
        password_hash=hash_password("pw"),
        role="guard",
        is_active=False,
    )
    db_session.add(user)
    db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/token",
            json={"username": "inactiveop", "password": "pw"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user_returns_401() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/token",
            json={"username": "nobody", "password": "pw"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_writes_audit_log(db_session: Session) -> None:
    from vms.db.models import AuditLog
    user = User(
        username="audited_op",
        password_hash=hash_password("pw123"),
        role="manager",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/api/auth/token",
            json={"username": "audited_op", "password": "pw123"},
        )
    db_session.flush()
    row = db_session.query(AuditLog).filter_by(event_type="LOGIN_SUCCESS").first()
    assert row is not None
    assert row.actor_user_id == user.user_id
```

- [x] **Step 5: Run tests to verify they fail**

```
pytest tests/test_api_auth.py -v
```
Expected: FAIL — route `/api/auth/token` not found (404).

- [x] **Step 6: Create `vms/api/routes/auth.py`**

```python
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
```

- [x] **Step 7: Register the router in `vms/api/main.py`**

```python
"""FastAPI application entry point."""
from __future__ import annotations

from fastapi import FastAPI

from vms.api.routes import auth, health, persons

app = FastAPI(title="VMS API", version="0.1.0")

app.include_router(auth.router, prefix="/api")
app.include_router(health.router, prefix="/api")
app.include_router(persons.router, prefix="/api")
```

- [x] **Step 8: Run tests to verify they pass**

```
pytest tests/test_api_auth.py -v
```
Expected: all PASS.

- [x] **Step 9: Run full suite**

```
pytest -v
```
Expected: all prior tests still PASS, new auth tests PASS.

- [x] **Step 10: Commit**

```
git add requirements.txt vms/api/deps.py vms/api/schemas.py vms/api/routes/auth.py vms/api/main.py tests/test_api_auth.py
git commit -m "feat(auth): add POST /api/auth/token login endpoint with audit trail"
```

---

## Task 5: Enforce roles on enrollment endpoints + filter purged in search

**Files:**
- Modify: `vms/api/routes/persons.py`
- Modify: `tests/test_api_persons.py`

- [x] **Step 1: Write the failing tests**

Add to `tests/test_api_persons.py`:

```python
def _auth_headers_role(role: str) -> dict[str, str]:
    from vms.api.deps import create_access_token
    token = create_access_token(user_id=99, role=role)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_person_guard_role_returns_403() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/persons",
            json={"name": "Bob", "employee_id": "E999"},
            headers=_auth_headers_role("guard"),
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_add_embedding_guard_role_returns_403(db_session: Session) -> None:
    from vms.db.models import Person
    person = Person(name="Alice", employee_id="EA1")
    db_session.add(person)
    db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/persons/{person.person_id}/embeddings",
            json={"embedding": [0.0] * 512, "quality_score": 0.9},
            headers=_auth_headers_role("guard"),
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_search_excludes_purged_persons(db_session: Session) -> None:
    from datetime import datetime, timezone
    from vms.db.models import Person
    active = Person(name="ActiveAlice", employee_id="AA1", is_active=True)
    purged = Person(name="ActiveAlice", employee_id="AA2", is_active=False,
                    purged_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db_session.add_all([active, purged])
    db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/persons/search?q=ActiveAlice",
            headers=_auth_headers_role("manager"),
        )
    assert response.status_code == 200
    results = response.json()
    ids = [r["employee_id"] for r in results]
    assert "AA1" in ids
    assert "AA2" not in ids
```

- [x] **Step 2: Run tests to verify they fail**

```
pytest tests/test_api_persons.py::test_create_person_guard_role_returns_403 tests/test_api_persons.py::test_add_embedding_guard_role_returns_403 tests/test_api_persons.py::test_search_excludes_purged_persons -v
```
Expected: FAIL (guard gets 201, search returns purged).

- [x] **Step 3: Apply fixes to `vms/api/routes/persons.py`**

Add a role check helper at the top of the file (after imports):

```python
_MANAGER_ROLES = {"manager", "admin"}

def _require_manager(user: dict[str, Any]) -> None:
    if user.get("role") not in _MANAGER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager role required")
```

In `create_person`, add the check as the first line of the function body:

```python
def create_person(
    body: PersonCreate,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Person:
    _require_manager(user)
    person = Person(name=body.name, employee_id=body.employee_id)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person
```

In `add_embedding`, add the check as first line:

```python
def add_embedding(
    person_id: int,
    body: EmbeddingCreate,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> PersonEmbedding:
    _require_manager(user)
    person = db.get(Person, person_id)
    ...
```

In `search_persons`, add `.filter(Person.is_active.is_(True))`:

```python
def search_persons(
    q: str,
    db: Session = Depends(get_db),  # noqa: B008
    _user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> list[Person]:
    return (
        db.query(Person)
        .filter(Person.is_active.is_(True))
        .filter(Person.name.ilike(f"%{q}%") | Person.employee_id.ilike(f"%{q}%"))
        .limit(50)
        .all()
    )
```

- [x] **Step 4: Run tests to verify they pass**

```
pytest tests/test_api_persons.py -v
```
Expected: all PASS (including existing tests that use admin/manager headers).

- [x] **Step 5: Commit**

```
git add vms/api/routes/persons.py tests/test_api_persons.py
git commit -m "fix(api): require manager role for enrollment; exclude purged persons from search"
```

---

## Task 6: Publish `faiss_dirty` events from enrollment and purge API

**Files:**
- Modify: `vms/api/deps.py`
- Modify: `vms/api/routes/persons.py`
- Modify: `tests/test_api_persons.py`

- [x] **Step 1: Add `get_api_redis` to `vms/api/deps.py`**

Add a module-level Redis singleton used by API endpoints for event publishing. Add after the existing imports:

```python
import redis.asyncio as aioredis


_api_redis: aioredis.Redis | None = None


def get_api_redis() -> aioredis.Redis:
    """Return a process-level Redis client for publishing faiss_dirty events."""
    global _api_redis
    if _api_redis is None:
        _api_redis = aioredis.from_url(  # type: ignore[no-untyped-call]
            get_settings().redis_url, decode_responses=True
        )
    return _api_redis
```

- [x] **Step 2: Write failing tests**

Add to `tests/test_api_persons.py`:

```python
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_add_embedding_publishes_faiss_add(db_session: Session) -> None:
    from vms.db.models import Person
    person = Person(name="FaissTest", employee_id="FT1")
    db_session.add(person)
    db_session.flush()

    with patch("vms.identity.faiss_dirty.publish_add", new_callable=AsyncMock) as mock_pub:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/persons/{person.person_id}/embeddings",
                json={"embedding": [0.1] * 512, "quality_score": 0.85},
                headers=_auth_headers("admin"),
            )
        assert response.status_code == 201
        mock_pub.assert_called_once()
        _, kwargs = mock_pub.call_args
        assert kwargs.get("person_id") == person.person_id or mock_pub.call_args[0][2] == person.person_id


@pytest.mark.asyncio
async def test_purge_publishes_faiss_remove(db_session: Session) -> None:
    import numpy as np
    from vms.db.models import Person, PersonEmbedding
    person = Person(name="PurgeMe", employee_id="PM1")
    db_session.add(person)
    db_session.flush()
    emb = PersonEmbedding(
        person_id=person.person_id,
        embedding=np.zeros(512, dtype=np.float32).tolist(),
        quality_score=0.9,
    )
    db_session.add(emb)
    db_session.flush()

    with patch("vms.identity.faiss_dirty.publish_remove", new_callable=AsyncMock) as mock_pub:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/api/persons/{person.person_id}",
                json={"confirmation_name": "PurgeMe", "reason": "GDPR erasure request"},
                headers=_auth_headers("admin"),
            )
        assert response.status_code == 204
        mock_pub.assert_called_once()
```

- [x] **Step 3: Run tests to verify they fail**

```
pytest tests/test_api_persons.py::test_add_embedding_publishes_faiss_add tests/test_api_persons.py::test_purge_publishes_faiss_remove -v
```
Expected: FAIL — `publish_add` / `publish_remove` never called.

- [x] **Step 4: Update `vms/api/routes/persons.py`** — make `add_embedding` and `purge_person` async

Replace the `add_embedding` function:

```python
@router.post(
    "/persons/{person_id}/embeddings",
    response_model=EmbeddingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_embedding(
    person_id: int,
    body: EmbeddingCreate,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> PersonEmbedding:
    _require_manager(user)
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    emb_array = np.array(body.embedding, dtype=np.float32)
    record = PersonEmbedding(
        person_id=person_id,
        embedding=emb_array,
        quality_score=body.quality_score,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    await faiss_dirty.publish_add(
        get_api_redis(), embedding_id=record.embedding_id, person_id=person_id
    )
    return record
```

Replace the `purge_person` function:

```python
@router.delete("/persons/{person_id}")
async def purge_person(
    person_id: int,
    body: PurgeRequest,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> Response:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    if person.name != body.confirmation_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="confirmation_name does not match person.name",
        )

    blank: list[float] = np.zeros(512, dtype=np.float32).tolist()
    embs = db.query(PersonEmbedding).filter_by(person_id=person_id).all()
    emb_ids = [e.embedding_id for e in embs]
    for emb in embs:
        emb.embedding = blank
        emb.quality_score = 0.0

    person.is_active = False
    person.purged_at = datetime.utcnow()
    person.thumbnail_path = None

    actor_id: int | None = int(user["sub"])
    if db.get(DBUser, actor_id) is None:
        actor_id = None

    write_audit_event(
        db,
        event_type="PERSON_PURGED",
        actor_user_id=actor_id,
        target_type="person",
        target_id=str(person_id),
        payload=body.reason,
    )

    await faiss_dirty.publish_remove(
        get_api_redis(), person_id=person_id, embedding_ids=emb_ids
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

Add the missing import at the top of `vms/api/routes/persons.py`:

```python
from vms.api.deps import get_api_redis, get_current_user, get_db
from vms.identity import faiss_dirty
```

- [x] **Step 5: Run tests to verify they pass**

```
pytest tests/test_api_persons.py -v
```
Expected: all PASS.

- [x] **Step 6: Run full suite**

```
pytest -v
```
Expected: all PASS.

- [x] **Step 7: Commit**

```
git add vms/api/deps.py vms/api/routes/persons.py tests/test_api_persons.py
git commit -m "feat(api): publish faiss_dirty add/remove events from enrollment and purge endpoints"
```

---

## Task 7: Fix audit hash-chain race condition (SELECT FOR UPDATE)

**Files:**
- Modify: `vms/db/audit.py`
- Modify: `tests/test_db_audit.py`

- [x] **Step 1: Write the failing test**

Add to `tests/test_db_audit.py`:

```python
import threading

def test_concurrent_writes_maintain_unique_prev_hashes(db_session: Session) -> None:
    """Two concurrent writes must not produce duplicate prev_hash values."""
    from vms.db.session import SessionLocal
    results: list[str] = []
    errors: list[Exception] = []

    def write_one() -> None:
        try:
            s = SessionLocal()
            try:
                row = write_audit_event(s, event_type="CONCURRENT_TEST")
                results.append(row.prev_hash)
            finally:
                s.close()
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=write_one)
    t2 = threading.Thread(target=write_one)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert not errors, f"Write errors: {errors}"
    assert len(results) == 2, "Both writes should succeed"
    assert results[0] != results[1], "prev_hash must differ — each links to a different prior row"
```

- [x] **Step 2: Run test to see current behaviour**

```
pytest tests/test_db_audit.py::test_concurrent_writes_maintain_unique_prev_hashes -v
```
This may pass or fail depending on timing. The fix makes it deterministic.

- [x] **Step 3: Fix `vms/db/audit.py` — add `with_for_update()`**

Replace the `last` query in `write_audit_event`:

```python
from sqlalchemy import select

def write_audit_event(
    session: Session,
    *,
    event_type: str,
    actor_user_id: int | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    payload: str | None = None,
) -> AuditLog:
    last = session.execute(
        select(AuditLog)
        .order_by(AuditLog.audit_id.desc())
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()

    prev_hash = last.row_hash if last is not None else _ZERO_HASH
    event_ts = datetime.now(timezone.utc).replace(tzinfo=None)
    # ... rest unchanged
```

Also update the import at the top of `vms/db/audit.py`:

```python
from datetime import datetime, timezone
```

And remove the old `from datetime import datetime` line, replacing it with the above.

- [x] **Step 4: Run tests to verify they pass**

```
pytest tests/test_db_audit.py -v
```
Expected: all PASS.

- [x] **Step 5: Commit**

```
git add vms/db/audit.py tests/test_db_audit.py
git commit -m "fix(audit): use SELECT FOR UPDATE to prevent hash-chain race under concurrent writes"
```

---

## Task 8: Handle malformed homography JSON gracefully

**Files:**
- Modify: `vms/identity/homography.py`
- Modify: `tests/test_identity_homography.py`

- [x] **Step 1: Write the failing test**

Add to `tests/test_identity_homography.py`:

```python
from vms.identity.homography import load_homography, project_to_floor

def test_load_homography_malformed_json_returns_none() -> None:
    result = load_homography("not valid json {{")
    assert result is None

def test_project_to_floor_malformed_json_returns_none() -> None:
    result = project_to_floor((100, 100, 200, 200), "not valid json {{")
    assert result is None
```

- [x] **Step 2: Run tests to verify they fail**

```
pytest tests/test_identity_homography.py::test_load_homography_malformed_json_returns_none -v
```
Expected: FAIL with `json.JSONDecodeError`.

- [x] **Step 3: Fix `vms/identity/homography.py`**

Replace `load_homography`:

```python
import json
import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def load_homography(homography_json: str | None) -> np.ndarray | None:  # type: ignore[type-arg]
    """Parse a camera's homography_matrix JSON into a (3, 3) float64 ndarray.

    Returns None if the input is None or malformed.
    """
    if homography_json is None:
        return None
    try:
        flat: list[float] = json.loads(homography_json)
        return np.array(flat, dtype=np.float64).reshape(3, 3)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Invalid homography_matrix JSON — skipping floor projection")
        return None
```

- [x] **Step 4: Run tests to verify they pass**

```
pytest tests/test_identity_homography.py -v
```
Expected: all PASS.

- [x] **Step 5: Commit**

```
git add vms/identity/homography.py tests/test_identity_homography.py
git commit -m "fix(identity): gracefully handle malformed homography JSON in load_homography"
```

---

## Task 9: Add `embedding` field to `Tracklet` + face-to-track association in InferenceEngine

**Background:** `DetectionFrame` currently carries `tracklets` (YOLO person tracks) and `face_embeddings` (SCRFD+AdaFace) as unrelated lists. `IdentityEngine.assign_global_track_id` needs an embedding per tracklet. We associate them by checking whether the face bbox centre falls inside the person bbox.

**Files:**
- Modify: `vms/inference/messages.py`
- Modify: `vms/inference/engine.py`
- Modify: `tests/test_inference_messages.py`
- Modify: `tests/test_inference_engine.py`

- [x] **Step 1: Write failing test for Tracklet embedding field**

Add to `tests/test_inference_messages.py`:

```python
from vms.inference.messages import Tracklet

def test_tracklet_has_embedding_field_defaulting_to_empty() -> None:
    t = Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 100, 100), confidence=0.9)
    assert t.embedding == ()

def test_tracklet_accepts_embedding() -> None:
    emb = tuple([0.1] * 512)
    t = Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 100, 100), confidence=0.9, embedding=emb)
    assert len(t.embedding) == 512
```

- [x] **Step 2: Run tests to verify they fail**

```
pytest tests/test_inference_messages.py::test_tracklet_has_embedding_field_defaulting_to_empty -v
```
Expected: FAIL — `Tracklet` has no `embedding` field.

- [x] **Step 3: Add `embedding` field to `Tracklet` in `vms/inference/messages.py`**

Find the `Tracklet` dataclass and add the field with a default:

```python
@dataclass(frozen=True)
class Tracklet:
    local_track_id: int
    camera_id: int
    bbox: tuple[int, int, int, int]
    confidence: float
    embedding: tuple[float, ...] = ()
```

`DetectionFrame.to_redis_fields` and `from_redis_fields` serialise `tracklets` as JSON. Update them to include embedding:

In `to_redis_fields`, the tracklets serialisation should include the embedding field. Find the existing serialisation and ensure `embedding` is included:

```python
# In DetectionFrame.to_redis_fields — update the tracklet dict to include embedding:
"tracklets": json.dumps([
    {
        "local_track_id": t.local_track_id,
        "camera_id": t.camera_id,
        "bbox": list(t.bbox),
        "confidence": t.confidence,
        "embedding": list(t.embedding),
    }
    for t in self.tracklets
]),
```

In `from_redis_fields`, update the `Tracklet` construction:

```python
tracklets=tuple(
    Tracklet(
        local_track_id=int(td["local_track_id"]),
        camera_id=int(td["camera_id"]),
        bbox=tuple(int(v) for v in td["bbox"]),  # type: ignore[arg-type]
        confidence=float(td["confidence"]),
        embedding=tuple(float(v) for v in td.get("embedding", [])),
    )
    for td in json.loads(fields["tracklets"])
),
```

- [x] **Step 4: Run tests to verify they pass**

```
pytest tests/test_inference_messages.py -v
```
Expected: all PASS.

- [x] **Step 5: Write failing test for face-to-track association**

Add to `tests/test_inference_engine.py`:

```python
from vms.inference.engine import _associate_faces
from vms.inference.messages import FaceWithEmbedding, Tracklet

def test_associate_faces_assigns_embedding_when_face_center_in_person_bbox() -> None:
    tracklets = (
        Tracklet(local_track_id=1, camera_id=1, bbox=(100, 100, 300, 400), confidence=0.9),
    )
    face_emb = tuple([0.1] * 512)
    faces = (
        FaceWithEmbedding(bbox=(150, 150, 250, 250), confidence=0.95, embedding=face_emb),
    )
    result = _associate_faces(tracklets, faces)
    assert result[1] == face_emb

def test_associate_faces_ignores_face_outside_all_bboxes() -> None:
    tracklets = (
        Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 100, 100), confidence=0.9),
    )
    faces = (
        FaceWithEmbedding(bbox=(500, 500, 600, 600), confidence=0.95, embedding=tuple([0.1] * 512)),
    )
    result = _associate_faces(tracklets, faces)
    assert 1 not in result

def test_associate_faces_ignores_face_with_empty_embedding() -> None:
    tracklets = (
        Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 300, 300), confidence=0.9),
    )
    faces = (
        FaceWithEmbedding(bbox=(50, 50, 150, 150), confidence=0.95, embedding=()),
    )
    result = _associate_faces(tracklets, faces)
    assert 1 not in result
```

- [x] **Step 6: Run tests to verify they fail**

```
pytest tests/test_inference_engine.py::test_associate_faces_assigns_embedding_when_face_center_in_person_bbox -v
```
Expected: FAIL — `_associate_faces` not defined.

- [x] **Step 7: Add `_associate_faces` + wire into `_process_one_message` in `vms/inference/engine.py`**

Add the helper function at module level (before the class):

```python
def _associate_faces(
    tracklets: tuple[Tracklet, ...],
    face_embeddings: tuple[FaceWithEmbedding, ...],
) -> dict[int, tuple[float, ...]]:
    """Map local_track_id → face embedding by face-centre-inside-person-bbox heuristic.

    Each face is assigned to the first tracklet whose bbox contains the face centre.
    Faces with empty embeddings are skipped.
    """
    result: dict[int, tuple[float, ...]] = {}
    for fw in face_embeddings:
        if not fw.embedding:
            continue
        fx = (fw.bbox[0] + fw.bbox[2]) // 2
        fy = (fw.bbox[1] + fw.bbox[3]) // 2
        for t in tracklets:
            if t.local_track_id in result:
                continue
            x1, y1, x2, y2 = t.bbox
            if x1 <= fx <= x2 and y1 <= fy <= y2:
                result[t.local_track_id] = fw.embedding
    return result
```

In `_process_one_message`, replace the section that builds `detection_frame`. Find:

```python
        tracker = self._trackers.get(pointer.cam_id)
        tracklets = tracker.update(frame_bgr) if tracker else []

        detection_frame = DetectionFrame(
            camera_id=pointer.cam_id,
            seq_id=seq_id,
            timestamp_ms=timestamp_ms,
            tracklets=tuple(tracklets),
            face_embeddings=tuple(face_embeddings),
        )
```

Replace with:

```python
        tracker = self._trackers.get(pointer.cam_id)
        raw_tracklets = tracker.update(frame_bgr) if tracker else []

        emb_map = _associate_faces(tuple(raw_tracklets), tuple(face_embeddings))
        enriched_tracklets = tuple(
            Tracklet(
                local_track_id=t.local_track_id,
                camera_id=t.camera_id,
                bbox=t.bbox,
                confidence=t.confidence,
                embedding=emb_map.get(t.local_track_id, ()),
            )
            for t in raw_tracklets
        )

        detection_frame = DetectionFrame(
            camera_id=pointer.cam_id,
            seq_id=seq_id,
            timestamp_ms=timestamp_ms,
            tracklets=enriched_tracklets,
            face_embeddings=tuple(face_embeddings),
        )
```

Add the `Tracklet` import to `vms/inference/engine.py` if not already present:

```python
from vms.inference.messages import DetectionFrame, Tracklet
```

- [x] **Step 8: Run tests to verify they pass**

```
pytest tests/test_inference_engine.py tests/test_inference_messages.py -v
```
Expected: all PASS.

- [x] **Step 9: Run full suite**

```
pytest -v
```
Expected: all PASS.

- [x] **Step 10: Commit**

```
git add vms/inference/messages.py vms/inference/engine.py tests/test_inference_messages.py tests/test_inference_engine.py
git commit -m "feat(inference): add Tracklet.embedding field and face-to-track association via centre-in-bbox"
```

---

## Task 10: Refactor ZonePresenceTracker — session per-call + zone caching

**Background:** Current `ZonePresenceTracker` holds a long-lived DB session (production leak) and re-queries all zones on every frame (performance). Fix: pass session into `update()`, cache zone polygons with TTL from `zone_cache_ttl_s` setting.

**Files:**
- Modify: `vms/identity/zone_presence.py`
- Modify: `tests/test_identity_zone_presence.py`

- [x] **Step 1: Write failing tests**

Add to `tests/test_identity_zone_presence.py`:

```python
from vms.identity.zone_presence import ZonePresenceTracker
from sqlalchemy.orm import Session

def test_tracker_constructed_without_session() -> None:
    """Tracker no longer takes a session at construction."""
    tracker = ZonePresenceTracker()
    assert tracker is not None

def test_tracker_update_accepts_session_parameter(db_session: Session) -> None:
    import uuid
    tracker = ZonePresenceTracker()
    # Should not raise even with no matching zone
    tracker.update(db_session, uuid.uuid4(), 1.0, 1.0)
```

- [x] **Step 2: Run tests to verify they fail**

```
pytest tests/test_identity_zone_presence.py::test_tracker_constructed_without_session -v
```
Expected: FAIL — `ZonePresenceTracker.__init__` requires `db`.

- [x] **Step 3: Rewrite `vms/identity/zone_presence.py`**

Replace the entire file:

```python
"""Zone presence state machine.

On each update():
  - Load zone polygons from DB (cached by zone_cache_ttl_s setting).
  - Find which zone (if any) the floor point falls in via point-in-polygon.
  - If entering a new zone: INSERT zone_presence (exited_at=NULL).
  - If leaving a zone: UPDATE exited_at on the open row.
  - If staying in same zone: no-op.

Session is passed per-call so the tracker can be long-lived without holding
a stale DB connection.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from vms.config import get_settings
from vms.db.models import Zone, ZonePresence

logger = logging.getLogger(__name__)


def point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test. polygon is a list of [x, y] pairs."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


class ZonePresenceTracker:
    """Tracks zone_presence rows for all active global_track_ids.

    Thread-safety: not thread-safe. Use one instance per worker process.
    """

    def __init__(self) -> None:
        self._current: dict[uuid.UUID, int | None] = {}  # gid -> current zone_id or None
        self._zones_cache: list[Zone] = []
        self._cache_expires_at: float = 0.0

    def _get_zones(self, db: Session) -> list[Zone]:
        now = time.monotonic()
        if now >= self._cache_expires_at:
            self._zones_cache = db.query(Zone).all()
            self._cache_expires_at = now + get_settings().zone_cache_ttl_s
        return self._zones_cache

    def update(
        self,
        db: Session,
        global_track_id: uuid.UUID,
        floor_x: float,
        floor_y: float,
    ) -> None:
        """Reconcile zone membership for one tracklet."""
        zones = self._get_zones(db)
        matched: int | None = None
        for z in zones:
            if z.polygon_json is None:
                continue
            try:
                poly: list[list[float]] = json.loads(z.polygon_json)
            except (json.JSONDecodeError, ValueError):
                continue
            if point_in_polygon(floor_x, floor_y, poly):
                matched = z.zone_id
                break

        prev = self._current.get(global_track_id)
        if matched == prev:
            return

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if prev is not None:
            self._close(db, global_track_id, prev, now_utc)
        if matched is not None:
            self._open(db, global_track_id, matched, now_utc)
        self._current[global_track_id] = matched

    def _open(self, db: Session, gid: uuid.UUID, zone_id: int, ts: datetime) -> None:
        db.add(ZonePresence(zone_id=zone_id, global_track_id=gid, entered_at=ts))

    def _close(self, db: Session, gid: uuid.UUID, zone_id: int, ts: datetime) -> None:
        db.flush()  # ensure any pending _open rows are visible to the query
        row = (
            db.query(ZonePresence)
            .filter_by(zone_id=zone_id, global_track_id=gid)
            .filter(ZonePresence.exited_at.is_(None))
            .first()
        )
        if row is not None:
            row.exited_at = ts
```

- [x] **Step 4: Update existing zone presence tests**

In `tests/test_identity_zone_presence.py`, update all existing test functions that call `ZonePresenceTracker(db_session)` → `ZonePresenceTracker()` (remove the session from the constructor) and update all calls from `tracker.update(gid, x, y)` → `tracker.update(db_session, gid, x, y)`.

Example before:
```python
tracker = ZonePresenceTracker(db_session)
tracker.update(gid, 5.0, 5.0)
```
Example after:
```python
tracker = ZonePresenceTracker()
tracker.update(db_session, gid, 5.0, 5.0)
```

- [x] **Step 5: Run tests to verify they pass**

```
pytest tests/test_identity_zone_presence.py -v
```
Expected: all PASS.

- [x] **Step 6: Run full suite**

```
pytest -v
```
Expected: all PASS.

- [x] **Step 7: Commit**

```
git add vms/identity/zone_presence.py tests/test_identity_zone_presence.py
git commit -m "refactor(identity): ZonePresenceTracker takes session per-call, caches zone polygons with TTL"
```

---

## Task 11: Add `evict_stale()` to `IdentityEngine` + use configurable `reid_stale_ms`

**Files:**
- Modify: `vms/identity/engine.py`
- Modify: `tests/test_identity_engine.py`

- [x] **Step 1: Write failing test**

Add to `tests/test_identity_engine.py`:

```python
import time
from vms.identity.engine import IdentityEngine
from vms.identity.reid import ReIdService
from vms.identity.faiss_index import FaissIndex

def _make_engine() -> IdentityEngine:
    return IdentityEngine(ReIdService(FaissIndex()))

def _unit_vec(seed: int = 0) -> tuple[float, ...]:
    import numpy as np
    rng = np.random.default_rng(seed)
    v = rng.random(512).astype(np.float32)
    return tuple((v / np.linalg.norm(v)).tolist())


def test_evict_stale_removes_old_entries() -> None:
    engine = _make_engine()
    now_ms = int(time.time() * 1000)
    old_ms = now_ms - 400_000  # 400 seconds ago > default 300_000 ms stale threshold

    # Directly insert a stale entry
    from vms.identity.engine import _TrackletEntry
    import uuid
    engine._registry[(1, 42)] = _TrackletEntry(
        global_track_id=uuid.uuid4(),
        person_id=None,
        last_embedding=None,
        last_seen_ms=old_ms,
        camera_id=1,
    )
    assert len(engine._registry) == 1
    evicted = engine.evict_stale(now_ms=now_ms)
    assert evicted == 1
    assert len(engine._registry) == 0


def test_evict_stale_keeps_fresh_entries() -> None:
    engine = _make_engine()
    now_ms = int(time.time() * 1000)
    recent_ms = now_ms - 10_000  # 10 seconds ago

    from vms.identity.engine import _TrackletEntry
    import uuid
    engine._registry[(1, 99)] = _TrackletEntry(
        global_track_id=uuid.uuid4(),
        person_id=None,
        last_embedding=None,
        last_seen_ms=recent_ms,
        camera_id=1,
    )
    evicted = engine.evict_stale(now_ms=now_ms)
    assert evicted == 0
    assert len(engine._registry) == 1
```

- [x] **Step 2: Run tests to verify they fail**

```
pytest tests/test_identity_engine.py::test_evict_stale_removes_old_entries -v
```
Expected: FAIL — `IdentityEngine` has no `evict_stale` method.

- [x] **Step 3: Update `vms/identity/engine.py`**

Remove the module-level constant:
```python
_STALE_MS = 5 * 60 * 1000  # DELETE this line
```

In `_cross_camera_match`, replace `_STALE_MS` with `settings.reid_stale_ms` (settings already called at line `settings = get_settings()`).

Replace:
```python
            if now_ms - entry.last_seen_ms > _STALE_MS:
```
With:
```python
            if now_ms - entry.last_seen_ms > settings.reid_stale_ms:
```

Add `evict_stale` method to the `IdentityEngine` class:

```python
    def evict_stale(self, now_ms: int | None = None) -> int:
        """Remove tracklets not seen within reid_stale_ms. Returns evicted count."""
        if now_ms is None:
            now_ms = time.time_ns() // 1_000_000
        threshold = get_settings().reid_stale_ms
        stale = [k for k, e in self._registry.items() if now_ms - e.last_seen_ms > threshold]
        for k in stale:
            del self._registry[k]
        return len(stale)
```

- [x] **Step 4: Run tests to verify they pass**

```
pytest tests/test_identity_engine.py -v
```
Expected: all PASS.

- [x] **Step 5: Commit**

```
git add vms/identity/engine.py tests/test_identity_engine.py
git commit -m "feat(identity): add IdentityEngine.evict_stale() and use configurable reid_stale_ms"
```

---

## Task 12: Wire IdentityEngine + homography + ZonePresenceTracker into DBWriter

**Background:** This is the core integration task. `flush_detection_frame` currently generates random `global_track_id` UUIDs. After this task it will call `IdentityEngine.assign_global_track_id`, look up the camera's homography, project the foot point to floor coordinates, and call `ZonePresenceTracker.update` — all within the same DB transaction as the `tracking_events` insert. `DBWriter` evicts stale identity entries every 1000 messages.

**Files:**
- Modify: `vms/writer/db_writer.py`
- Modify: `tests/test_db_writer.py`

- [x] **Step 1: Write failing tests**

Add to `tests/test_db_writer.py`:

```python
import uuid
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session
from vms.inference.messages import DetectionFrame, Tracklet
from vms.writer.db_writer import flush_detection_frame
from vms.identity.engine import IdentityEngine
from vms.identity.faiss_index import FaissIndex
from vms.identity.reid import ReIdService
from vms.identity.zone_presence import ZonePresenceTracker
from vms.db.models import Camera, TrackingEvent
import pytest


def _make_frame(camera_id: int = 1, track_id: int = 7) -> DetectionFrame:
    return DetectionFrame(
        camera_id=camera_id,
        seq_id=1,
        timestamp_ms=1_700_000_000_000,
        tracklets=(
            Tracklet(
                local_track_id=track_id,
                camera_id=camera_id,
                bbox=(10, 20, 110, 220),
                confidence=0.9,
                embedding=tuple([0.1] * 512),
            ),
        ),
        face_embeddings=(),
    )


@pytest.mark.integration
def test_flush_uses_identity_engine_for_global_track_id(db_session: Session) -> None:
    cam = Camera(name="Cam1", rtsp_url="rtsp://x/1", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()

    engine = IdentityEngine(ReIdService(FaissIndex()))
    zone_tracker = ZonePresenceTracker()
    frame = _make_frame(camera_id=cam.camera_id, track_id=5)

    flush_detection_frame(
        db_session,
        frame,
        identity=engine,
        homography_json=None,
        zone_tracker=zone_tracker,
    )
    db_session.flush()

    row = db_session.query(TrackingEvent).filter_by(
        camera_id=cam.camera_id, local_track_id="5"
    ).first()
    assert row is not None
    gid1 = row.global_track_id

    # Second flush of same tracklet must reuse the same global_track_id
    flush_detection_frame(
        db_session,
        DetectionFrame(
            camera_id=cam.camera_id,
            seq_id=2,
            timestamp_ms=1_700_000_001_000,
            tracklets=(
                Tracklet(local_track_id=5, camera_id=cam.camera_id,
                         bbox=(10, 20, 110, 220), confidence=0.9),
            ),
            face_embeddings=(),
        ),
        identity=engine,
        homography_json=None,
        zone_tracker=zone_tracker,
    )
    db_session.flush()

    rows = db_session.query(TrackingEvent).filter_by(
        camera_id=cam.camera_id, local_track_id="5"
    ).all()
    # Second event_ts differs so both rows exist; global_track_id must match
    assert all(r.global_track_id == gid1 for r in rows)


@pytest.mark.integration
def test_flush_without_identity_still_works(db_session: Session) -> None:
    """Backward-compat: flush_detection_frame with identity=None uses random UUID."""
    cam = Camera(name="Cam2", rtsp_url="rtsp://x/2", capability_tier="FULL")
    db_session.add(cam)
    db_session.flush()

    frame = _make_frame(camera_id=cam.camera_id)
    flush_detection_frame(db_session, frame)
    db_session.flush()

    row = db_session.query(TrackingEvent).filter_by(camera_id=cam.camera_id).first()
    assert row is not None
    assert row.global_track_id is not None
```

- [x] **Step 2: Run tests to verify they fail**

```
pytest tests/test_db_writer.py::test_flush_uses_identity_engine_for_global_track_id -v
```
Expected: FAIL — `flush_detection_frame` ignores `identity` kwarg.

- [x] **Step 3: Update `vms/writer/db_writer.py`**

Replace the entire file:

```python
"""Batch inserts DetectionFrame tracklets into tracking_events.

Uses INSERT ... ON CONFLICT DO NOTHING for idempotent replay (CLAUDE.md §6.3).
The unique constraint uq_tracking_idem is on (camera_id, local_track_id, event_ts).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.orm import Session

from vms.db.models import Camera
from vms.identity.engine import IdentityEngine
from vms.identity.homography import project_to_floor
from vms.identity.zone_presence import ZonePresenceTracker
from vms.inference.messages import DetectionFrame
from vms.redis_client import stream_read

logger = logging.getLogger(__name__)

_DETECTIONS_STREAM = "detections"
_EVICT_EVERY = 1000  # evict stale registry entries every N messages

_INSERT_SQL = text(
    """
    INSERT INTO tracking_events
        (camera_id, local_track_id, global_track_id, person_id,
         bbox_x1, bbox_y1, bbox_x2, bbox_y2,
         floor_x, floor_y,
         event_ts, ingest_ts, seq_id)
    VALUES
        (:camera_id, :local_track_id, :global_track_id, :person_id,
         :bbox_x1, :bbox_y1, :bbox_x2, :bbox_y2,
         :floor_x, :floor_y,
         :event_ts, :ingest_ts, :seq_id)
    ON CONFLICT ON CONSTRAINT uq_tracking_idem DO NOTHING
    """
)


def flush_detection_frame(
    db: Session,
    frame: DetectionFrame,
    *,
    identity: IdentityEngine | None = None,
    homography_json: str | None = None,
    zone_tracker: ZonePresenceTracker | None = None,
) -> None:
    """Write all tracklets from one DetectionFrame to tracking_events (idempotent).

    When identity is provided, global_track_id and person_id are resolved through
    IdentityEngine rather than generated randomly.
    """
    if not frame.tracklets:
        return

    event_ts = datetime.fromtimestamp(frame.timestamp_ms / 1000.0, tz=timezone.utc).replace(
        tzinfo=None
    )
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    rows = []
    for t in frame.tracklets:
        embedding = t.embedding if t.embedding else None

        if identity is not None:
            gid = identity.assign_global_track_id(t.camera_id, t.local_track_id, embedding)
            person_id = identity.identify_person(embedding) if embedding else None
        else:
            gid = uuid.uuid4()
            person_id = None

        floor_coords = project_to_floor(t.bbox, homography_json) if homography_json else None
        floor_x = floor_coords[0] if floor_coords else None
        floor_y = floor_coords[1] if floor_coords else None

        if zone_tracker is not None and floor_coords is not None:
            zone_tracker.update(db, gid, floor_x, floor_y)  # type: ignore[arg-type]

        rows.append(
            {
                "camera_id": t.camera_id,
                "local_track_id": str(t.local_track_id),
                "global_track_id": str(gid),
                "person_id": person_id,
                "bbox_x1": t.bbox[0],
                "bbox_y1": t.bbox[1],
                "bbox_x2": t.bbox[2],
                "bbox_y2": t.bbox[3],
                "floor_x": floor_x,
                "floor_y": floor_y,
                "event_ts": event_ts,
                "ingest_ts": now_utc,
                "seq_id": frame.seq_id,
            }
        )
    db.execute(_INSERT_SQL, rows)


class DBWriter:
    """Consumes the 'detections' Redis stream and batch-writes to tracking_events."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        db_factory: type[Session],
        identity: IdentityEngine | None = None,
        zone_tracker: ZonePresenceTracker | None = None,
    ) -> None:
        self._redis = redis_client
        self._db_factory = db_factory
        self._identity = identity
        self._zone_tracker = zone_tracker
        self._running = False
        self._last_id = "0-0"
        self._msg_count = 0
        self._cam_homography: dict[int, str | None] = {}

    def _get_homography(self, db: Session, camera_id: int) -> str | None:
        if camera_id not in self._cam_homography:
            cam = db.get(Camera, camera_id)
            self._cam_homography[camera_id] = cam.homography_matrix if cam else None
        return self._cam_homography[camera_id]

    async def run(self) -> None:
        self._running = True
        while self._running:
            messages = await stream_read(
                self._redis, _DETECTIONS_STREAM, last_id=self._last_id, count=100
            )
            if messages:
                db = self._db_factory()
                try:
                    for msg_id, fields in messages:
                        frame = DetectionFrame.from_redis_fields(fields)
                        homography_json = self._get_homography(db, frame.camera_id)
                        flush_detection_frame(
                            db,
                            frame,
                            identity=self._identity,
                            homography_json=homography_json,
                            zone_tracker=self._zone_tracker,
                        )
                        self._last_id = msg_id
                        self._msg_count += 1

                    if self._identity is not None and self._msg_count % _EVICT_EVERY == 0:
                        evicted = self._identity.evict_stale()
                        if evicted:
                            logger.debug("evicted %d stale tracklets", evicted)

                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("DB writer flush failed")
                finally:
                    db.close()
            else:
                await asyncio.sleep(0.05)

    async def stop(self) -> None:
        self._running = False
```

- [x] **Step 4: Run tests to verify they pass**

```
pytest tests/test_db_writer.py -v
```
Expected: all PASS.

- [x] **Step 5: Run lint, type check, full suite**

```
ruff check vms/ tests/
mypy vms/
pytest -v
```
Expected: all clean and all PASS.

- [x] **Step 6: Commit**

```
git add vms/writer/db_writer.py tests/test_db_writer.py
git commit -m "feat(writer): wire IdentityEngine + homography + ZonePresenceTracker into DBWriter"
```

---

## Final Verification

All 12 tasks complete. Final quality gate passed:

- **159 tests passing** (up from 128)
- **mypy strict clean**
- **ruff clean**
- **Coverage ≥ 80%** on `vms/db`, `vms/api`, `vms/identity`

Phase 2a Hardening is now complete and production-ready.
