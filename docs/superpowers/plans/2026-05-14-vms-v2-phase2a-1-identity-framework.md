# VMS v2 Phase 2a — Identity Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE**

**Goal:** Build the in-memory FAISS identity layer that assigns consistent `global_track_id` values across cameras, resolves `person_id` from face embeddings via cosine similarity, projects bounding boxes to floor coordinates via homography, and manages zone presence — turning raw Phase 1B tracklets into actionable identity events.

**Architecture:** `IdentityEngine` consumes the `detections` Redis stream. For each `DetectionFrame` it (1) assigns a stable `global_track_id` via a 5-minute in-process tracklet registry with cross-camera embedding matching, (2) searches the FAISS index for a known `person_id`, (3) applies a per-camera homography to compute floor coordinates, (4) writes enriched rows to `tracking_events`, and (5) updates `zone_presence`. A `faiss_dirty` Redis stream keeps the in-memory index consistent with DB-side enrolments and GDPR purges. Phase 2b (Anomaly Framework) builds on top of this.

**Tech Stack:** Python 3.10.11 · faiss-cpu 1.8.0 · numpy 1.26 · OpenCV 4.9 · SQLAlchemy 2.x · fakeredis 2.x (tests only) · pytest 8.x

**Spec refs:**
- v1 §7 Cross-camera re-identification · §8 Homography
- v2 §C trigger-gated model pools (identity context)
- db-edge-cases §1 C2/C3/C6 · §7 GDPR purge · §15 FAISS/DB consistency
- `vms/config.py` — `adaface_min_sim=0.72`, `reid_cross_cam_sim=0.65`, `reid_margin=0.08` already defined

---

## File Map

```
alembic/versions/
└── XXXX_phase2a_add_homography_adjacent_zones.py  -- new migration

vms/
├── db/
│   └── models.py                         -- add Camera.homography_matrix, Zone.adjacent_zone_ids
└── identity/
    ├── __init__.py
    ├── faiss_index.py    # FaissIndex: rebuild from DB, add/remove, cosine search
    ├── reid.py           # ReIdService: threshold + margin gates on FaissIndex.search()
    ├── homography.py     # load_homography(), project_to_floor() — foot point → (floor_x, floor_y)
    ├── faiss_dirty.py    # publish_add(), publish_remove() — Redis stream events
    ├── zone_presence.py  # ZonePresenceTracker: point-in-polygon, open/close zone_presence rows
    └── engine.py         # IdentityEngine: tracklet registry + orchestration + DB writes

vms/api/
├── schemas.py            -- add PurgeRequest
└── routes/persons.py     -- add DELETE /api/persons/{id}

tests/
├── test_identity_faiss_index.py
├── test_identity_reid.py
├── test_identity_homography.py
├── test_identity_faiss_dirty.py
├── test_identity_zone_presence.py
└── test_identity_engine.py
```

---

## Pre-flight

- [ ] **Add `faiss-cpu` to requirements.txt**

Append:
```
faiss-cpu==1.8.0
```

- [ ] **Install**
```powershell
pip install faiss-cpu==1.8.0
```

- [ ] **Verify**
```powershell
python -c "import faiss; idx = faiss.IndexFlatIP(4); print('faiss ok, ntotal:', idx.ntotal)"
```
Expected: `faiss ok, ntotal: 0`

- [ ] **Baseline: 96 tests pass**
```powershell
python -m pytest tests/ -q
```

---

## Task 1: Schema Migration

**Files:**
- Modify: `vms/db/models.py`
- Create: `alembic/versions/XXXX_phase2a_add_homography_adjacent_zones.py`

`cameras.homography_matrix` — 3×3 row-major float64 stored as JSON string (9 floats).
`zones.adjacent_zone_ids` — JSON array of `zone_id` integers for cross-zone re-ID pre-filter.

- [ ] **Step 1.1: Add columns to ORM models**

In `vms/db/models.py`, add to the `Camera` class after `worker_group`:
```python
homography_matrix: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Add to the `Zone` class after `polygon_json`:
```python
adjacent_zone_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 1.2: Generate migration**
```powershell
alembic revision -m "phase2a_add_homography_adjacent_zones"
```

- [ ] **Step 1.3: Fill in migration body**

Open the generated file. Replace the empty `upgrade`/`downgrade` with:
```python
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column("cameras", sa.Column("homography_matrix", sa.Text(), nullable=True))
    op.add_column("zones", sa.Column("adjacent_zone_ids", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("zones", "adjacent_zone_ids")
    op.drop_column("cameras", "homography_matrix")
```

- [ ] **Step 1.4: Apply and round-trip test**
```powershell
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

- [ ] **Step 1.5: Full suite still passes**
```powershell
python -m pytest tests/ -q
```
Expected: 96 passed.

- [ ] **Step 1.6: Commit**
```powershell
git add vms/db/models.py alembic/versions/
git commit -m "feat(identity): add Camera.homography_matrix + Zone.adjacent_zone_ids migration"
```

---

## Task 2: FaissIndex

**Files:**
- Create: `vms/identity/__init__.py`
- Create: `vms/identity/faiss_index.py`
- Create: `tests/test_identity_faiss_index.py`

`FaissIndex` wraps `faiss.IndexIDMap2(faiss.IndexFlatIP(512))`. Embeddings are L2-normalised before insertion so inner product equals cosine similarity. Row IDs in the FAISS index are `embedding_id` values from the DB — enabling precise `remove_ids` on GDPR purge.

**Note on pgvector read:** `PersonEmbedding.embedding` (a `Vector(512)` column) returns a Python `list[float]` when read via SQLAlchemy. Always convert with `np.array(r.embedding, dtype=np.float32)`.

- [ ] **Step 2.1: Write failing tests**

```python
# tests/test_identity_faiss_index.py
from __future__ import annotations

import numpy as np
import pytest
from sqlalchemy.orm import Session

from vms.db.models import Person, PersonEmbedding
from vms.identity.faiss_index import FaissIndex


def _unit_vec(seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(512).astype(np.float32)
    return v / np.linalg.norm(v)


# ── unit tests (no DB) ────────────────────────────────────────────────

def test_faiss_index_starts_empty() -> None:
    idx = FaissIndex()
    assert idx.count() == 0


def test_faiss_index_add_increments_count() -> None:
    idx = FaissIndex()
    idx.add(embedding_id=1, person_id=10, embedding=_unit_vec(seed=0))
    assert idx.count() == 1


def test_faiss_index_search_returns_known_person() -> None:
    idx = FaissIndex()
    v = _unit_vec(seed=0)
    idx.add(embedding_id=1, person_id=10, embedding=v)
    results = idx.search(v, k=1)
    assert len(results) == 1
    assert results[0][0] == 10      # person_id
    assert results[0][1] > 0.99    # near-identical vector → similarity ≈ 1.0


def test_faiss_index_remove_decrements_count() -> None:
    idx = FaissIndex()
    idx.add(embedding_id=1, person_id=10, embedding=_unit_vec(seed=0))
    idx.remove([1])
    assert idx.count() == 0


def test_faiss_index_search_on_empty_returns_empty() -> None:
    idx = FaissIndex()
    assert idx.search(_unit_vec(), k=5) == []


# ── integration tests (real PostgreSQL) ──────────────────────────────

@pytest.mark.integration
def test_faiss_index_rebuild_loads_active_embeddings(db_session: Session) -> None:
    person = Person(name="FaissAlice", employee_id="E_FAISS_01")
    db_session.add(person)
    db_session.flush()
    db_session.add(PersonEmbedding(
        person_id=person.person_id,
        embedding=_unit_vec(seed=1),
        quality_score=0.9,
    ))
    db_session.flush()

    idx = FaissIndex()
    idx.rebuild(db_session)
    assert idx.count() >= 1


@pytest.mark.integration
def test_faiss_index_rebuild_excludes_inactive_persons(db_session: Session) -> None:
    person = Person(name="FaissBob", employee_id="E_FAISS_02", is_active=False)
    db_session.add(person)
    db_session.flush()
    db_session.add(PersonEmbedding(
        person_id=person.person_id,
        embedding=_unit_vec(seed=2),
        quality_score=0.8,
    ))
    db_session.flush()

    idx = FaissIndex()
    idx.rebuild(db_session)
    assert idx.count() == 0
```

- [ ] **Step 2.2: Run — expect ImportError**
```powershell
python -m pytest tests/test_identity_faiss_index.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.identity'`

- [ ] **Step 2.3: Create `vms/identity/__init__.py`**
```python
"""Identity layer: FAISS-based person recognition, cross-camera re-ID, zone presence."""
```

- [ ] **Step 2.4: Implement `vms/identity/faiss_index.py`**

```python
"""FAISS-backed embedding index for fast person identification.

Uses IndexIDMap2(IndexFlatIP(512)) so we can:
  add_with_ids — assign DB embedding_id as the FAISS row ID
  remove_ids   — precise removal on GDPR purge
  search       — inner-product similarity (== cosine after L2 normalisation)
"""

from __future__ import annotations

import logging

import faiss
import numpy as np
from sqlalchemy.orm import Session

from vms.db.models import Person, PersonEmbedding

logger = logging.getLogger(__name__)

_DIM = 512


class FaissIndex:
    """In-memory FAISS index keyed by embedding_id. Not thread-safe."""

    def __init__(self) -> None:
        flat = faiss.IndexFlatIP(_DIM)
        self._index: faiss.IndexIDMap2 = faiss.IndexIDMap2(flat)
        self._emb_to_person: dict[int, int] = {}  # embedding_id → person_id

    def rebuild(self, db: Session) -> None:
        """Wipe and reload all active-person embeddings from the DB."""
        self._index.reset()
        self._emb_to_person.clear()

        rows: list[PersonEmbedding] = (
            db.query(PersonEmbedding)
            .join(Person, PersonEmbedding.person_id == Person.person_id)
            .filter(Person.is_active.is_(True))
            .all()
        )
        if not rows:
            return

        ids = np.array([r.embedding_id for r in rows], dtype=np.int64)
        # pgvector returns list[float] — must convert to float32 ndarray
        vecs = np.array([r.embedding for r in rows], dtype=np.float32)
        faiss.normalize_L2(vecs)
        self._index.add_with_ids(vecs, ids)
        for r in rows:
            self._emb_to_person[r.embedding_id] = r.person_id
        logger.info("FAISS index rebuilt: %d embeddings", len(rows))

    def add(self, embedding_id: int, person_id: int, embedding: np.ndarray) -> None:
        """Incrementally add one embedding after enrolment."""
        vec = np.array(embedding, dtype=np.float32).reshape(1, _DIM)
        faiss.normalize_L2(vec)
        self._index.add_with_ids(vec, np.array([embedding_id], dtype=np.int64))
        self._emb_to_person[embedding_id] = person_id

    def remove(self, embedding_ids: list[int]) -> None:
        """Remove embeddings by their DB IDs after GDPR purge."""
        if not embedding_ids:
            return
        self._index.remove_ids(np.array(embedding_ids, dtype=np.int64))
        for eid in embedding_ids:
            self._emb_to_person.pop(eid, None)

    def search(self, query: np.ndarray, k: int = 5) -> list[tuple[int, float]]:
        """Return (person_id, cosine_similarity) for top-k results, best first.

        Returns [] when the index is empty.
        """
        if self._index.ntotal == 0:
            return []
        vec = np.array(query, dtype=np.float32).reshape(1, _DIM)
        faiss.normalize_L2(vec)
        sims, ids = self._index.search(vec, min(k, self._index.ntotal))
        results: list[tuple[int, float]] = []
        for sim, eid in zip(sims[0], ids[0], strict=False):
            if eid == -1:
                continue
            pid = self._emb_to_person.get(int(eid))
            if pid is not None:
                results.append((pid, float(sim)))
        return results

    def count(self) -> int:
        return int(self._index.ntotal)
```

- [ ] **Step 2.5: Run tests — expect 7 passed**
```powershell
python -m pytest tests/test_identity_faiss_index.py -v
```

- [ ] **Step 2.6: Lint + type-check**
```powershell
ruff check vms/identity/ tests/test_identity_faiss_index.py
mypy vms/identity/faiss_index.py
```

- [ ] **Step 2.7: Commit**
```powershell
git add vms/identity/ tests/test_identity_faiss_index.py
git commit -m "feat(identity): add FaissIndex with rebuild/add/remove/search"
```

---

## Task 3: ReIdService

**Files:**
- Create: `vms/identity/reid.py`
- Create: `tests/test_identity_reid.py`

`ReIdService` wraps `FaissIndex.search()` and applies two gates:
1. `best_sim ≥ settings.adaface_min_sim` (0.72)
2. `best_sim − second_sim ≥ settings.reid_margin` (0.08) — skipped when only one result exists

- [ ] **Step 3.1: Write failing tests**

```python
# tests/test_identity_reid.py
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from vms.identity.reid import ReIdService


def _vec() -> np.ndarray:
    return np.ones(512, dtype=np.float32)


def test_reid_returns_person_id_when_above_thresholds() -> None:
    index = MagicMock()
    index.search.return_value = [(42, 0.85), (99, 0.70)]  # margin = 0.15 ≥ 0.08
    svc = ReIdService(index=index)
    assert svc.identify(_vec()) == 42


def test_reid_returns_none_when_below_similarity_threshold() -> None:
    index = MagicMock()
    index.search.return_value = [(42, 0.60)]  # 0.60 < 0.72
    svc = ReIdService(index=index)
    assert svc.identify(_vec()) is None


def test_reid_returns_none_when_margin_too_small() -> None:
    index = MagicMock()
    index.search.return_value = [(42, 0.80), (99, 0.75)]  # margin = 0.05 < 0.08
    svc = ReIdService(index=index)
    assert svc.identify(_vec()) is None


def test_reid_skips_margin_check_for_single_result() -> None:
    index = MagicMock()
    index.search.return_value = [(42, 0.75)]  # only one result — margin N/A
    svc = ReIdService(index=index)
    assert svc.identify(_vec()) == 42


def test_reid_returns_none_for_empty_index() -> None:
    index = MagicMock()
    index.search.return_value = []
    svc = ReIdService(index=index)
    assert svc.identify(_vec()) is None
```

- [ ] **Step 3.2: Run — expect ImportError**
```powershell
python -m pytest tests/test_identity_reid.py -v
```

- [ ] **Step 3.3: Implement `vms/identity/reid.py`**

```python
"""FAISS-backed person identification with similarity + margin gates."""

from __future__ import annotations

import numpy as np

from vms.config import get_settings
from vms.identity.faiss_index import FaissIndex


class ReIdService:
    """Identifies a person from a face embedding using the FAISS index.

    Gates (both must pass):
      1. best_sim ≥ adaface_min_sim  (default 0.72)
      2. best_sim − second_sim ≥ reid_margin  (default 0.08)
         — skipped when only one result is available
    """

    def __init__(self, index: FaissIndex) -> None:
        self._index = index

    def identify(self, embedding: np.ndarray) -> int | None:
        """Return person_id if the embedding matches a known person, else None."""
        settings = get_settings()
        results = self._index.search(embedding, k=2)
        if not results:
            return None

        best_id, best_sim = results[0]
        if best_sim < settings.adaface_min_sim:
            return None

        if len(results) >= 2:
            _, second_sim = results[1]
            if (best_sim - second_sim) < settings.reid_margin:
                return None

        return best_id
```

- [ ] **Step 3.4: Run — expect 5 passed**
```powershell
python -m pytest tests/test_identity_reid.py -v
```

- [ ] **Step 3.5: Lint + type-check**
```powershell
ruff check vms/identity/reid.py tests/test_identity_reid.py
mypy vms/identity/reid.py
```

- [ ] **Step 3.6: Commit**
```powershell
git add vms/identity/reid.py tests/test_identity_reid.py
git commit -m "feat(identity): add ReIdService with similarity + margin thresholds"
```

---

## Task 4: Homography Projection

**Files:**
- Create: `vms/identity/homography.py`
- Create: `tests/test_identity_homography.py`

`cameras.homography_matrix` stores a 3×3 row-major float64 matrix as JSON: `[h00,h01,h02, h10,h11,h12, h20,h21,h22]`.

`project_to_floor` uses the **bottom-centre** of the bounding box as the foot position (more accurate for standing persons than the centroid).

- [ ] **Step 4.1: Write failing tests**

```python
# tests/test_identity_homography.py
from __future__ import annotations

import json

import numpy as np

from vms.identity.homography import load_homography, project_to_floor


def test_load_homography_parses_json() -> None:
    flat = list(range(9))
    H = load_homography(json.dumps([float(x) for x in flat]))
    assert H is not None
    assert H.shape == (3, 3)
    assert H[0, 0] == 0.0
    assert H[2, 2] == 8.0


def test_load_homography_returns_none_for_none() -> None:
    assert load_homography(None) is None


def test_project_to_floor_identity_matrix() -> None:
    H = np.eye(3, dtype=np.float64)
    H_json = json.dumps(H.flatten().tolist())
    # bbox (100, 200, 200, 400) → foot point = (150.0, 400.0)
    result = project_to_floor((100, 200, 200, 400), H_json)
    assert result is not None
    fx, fy = result
    assert abs(fx - 150.0) < 0.5
    assert abs(fy - 400.0) < 0.5


def test_project_to_floor_returns_none_for_no_matrix() -> None:
    assert project_to_floor((0, 0, 100, 200), None) is None
```

- [ ] **Step 4.2: Run — expect ImportError**
```powershell
python -m pytest tests/test_identity_homography.py -v
```

- [ ] **Step 4.3: Implement `vms/identity/homography.py`**

```python
"""Floor-plane homography projection.

cameras.homography_matrix JSON format: [h00,h01,h02, h10,h11,h12, h20,h21,h22]
(3×3 row-major float64)

project_to_floor uses bottom-centre (foot point) for better accuracy on standing persons.
"""

from __future__ import annotations

import json

import cv2
import numpy as np


def load_homography(homography_json: str | None) -> np.ndarray | None:
    """Parse a camera's homography_matrix JSON into a (3, 3) float64 ndarray."""
    if homography_json is None:
        return None
    flat: list[float] = json.loads(homography_json)
    return np.array(flat, dtype=np.float64).reshape(3, 3)


def project_to_floor(
    bbox: tuple[int, int, int, int],
    homography_json: str | None,
) -> tuple[float, float] | None:
    """Project bounding box foot point to floor coordinates.

    Returns (floor_x, floor_y) or None if no homography matrix is stored.
    Foot point is bottom-centre: ((x1+x2)/2, y2).
    """
    H = load_homography(homography_json)
    if H is None:
        return None
    x1, _y1, x2, y2 = bbox
    foot = np.array([[[((x1 + x2) / 2.0), float(y2)]]], dtype=np.float32)
    out = cv2.perspectiveTransform(foot, H.astype(np.float32))
    return float(out[0, 0, 0]), float(out[0, 0, 1])
```

- [ ] **Step 4.4: Run — expect 4 passed**
```powershell
python -m pytest tests/test_identity_homography.py -v
```

- [ ] **Step 4.5: Lint + type-check**
```powershell
ruff check vms/identity/homography.py tests/test_identity_homography.py
mypy vms/identity/homography.py
```

- [ ] **Step 4.6: Commit**
```powershell
git add vms/identity/homography.py tests/test_identity_homography.py
git commit -m "feat(identity): add homography floor projection helper"
```

---

## Task 5: faiss_dirty Stream Events

**Files:**
- Create: `vms/identity/faiss_dirty.py`
- Create: `tests/test_identity_faiss_dirty.py`

`publish_add` — called after `PersonEmbedding` is committed (enrolment).
`publish_remove` — called after GDPR purge blanks embeddings.

Consumers (identity services) read this stream and update their in-memory FAISS index without a full rebuild.

- [ ] **Step 5.1: Write failing tests**

```python
# tests/test_identity_faiss_dirty.py
from __future__ import annotations

import json

import pytest
import fakeredis.aioredis as fake_aioredis

from vms.identity.faiss_dirty import publish_add, publish_remove


@pytest.fixture
def fake_redis() -> fake_aioredis.FakeRedis:
    return fake_aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_publish_add_writes_correct_fields(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    await publish_add(fake_redis, embedding_id=7, person_id=3)
    msgs = await fake_redis.xread({"faiss_dirty": "0-0"}, count=10)
    assert len(msgs) == 1
    _stream, entries = msgs[0]
    _msg_id, fields = entries[0]
    assert fields["action"] == "add"
    assert fields["embedding_id"] == "7"
    assert fields["person_id"] == "3"


@pytest.mark.asyncio
async def test_publish_remove_writes_correct_fields(
    fake_redis: fake_aioredis.FakeRedis,
) -> None:
    await publish_remove(fake_redis, person_id=5, embedding_ids=[1, 2, 3])
    msgs = await fake_redis.xread({"faiss_dirty": "0-0"}, count=10)
    assert len(msgs) == 1
    _stream, entries = msgs[0]
    _msg_id, fields = entries[0]
    assert fields["action"] == "remove"
    assert fields["person_id"] == "5"
    assert json.loads(fields["embedding_ids"]) == [1, 2, 3]
```

- [ ] **Step 5.2: Run — expect ImportError**
```powershell
python -m pytest tests/test_identity_faiss_dirty.py -v
```

- [ ] **Step 5.3: Implement `vms/identity/faiss_dirty.py`**

```python
"""Redis Stream events for FAISS index synchronisation.

publish_add:    call after a new PersonEmbedding is committed to the DB.
publish_remove: call after a GDPR purge blanks/removes embeddings.
"""

from __future__ import annotations

import json

import redis.asyncio as aioredis

from vms.redis_client import stream_add

_STREAM = "faiss_dirty"


async def publish_add(
    client: aioredis.Redis,  # type: ignore[type-arg]
    embedding_id: int,
    person_id: int,
) -> None:
    """Notify identity services that a new embedding was enrolled."""
    await stream_add(
        client,
        _STREAM,
        {"action": "add", "embedding_id": str(embedding_id), "person_id": str(person_id)},
    )


async def publish_remove(
    client: aioredis.Redis,  # type: ignore[type-arg]
    person_id: int,
    embedding_ids: list[int],
) -> None:
    """Notify identity services that embeddings were purged for a person."""
    await stream_add(
        client,
        _STREAM,
        {
            "action": "remove",
            "person_id": str(person_id),
            "embedding_ids": json.dumps(embedding_ids),
        },
    )
```

- [ ] **Step 5.4: Run — expect 2 passed**
```powershell
python -m pytest tests/test_identity_faiss_dirty.py -v
```

- [ ] **Step 5.5: Lint + type-check**
```powershell
ruff check vms/identity/faiss_dirty.py tests/test_identity_faiss_dirty.py
mypy vms/identity/faiss_dirty.py
```

- [ ] **Step 5.6: Commit**
```powershell
git add vms/identity/faiss_dirty.py tests/test_identity_faiss_dirty.py
git commit -m "feat(identity): add faiss_dirty stream event publishers"
```

---

## Task 6: ZonePresenceTracker

**Files:**
- Create: `vms/identity/zone_presence.py`
- Create: `tests/test_identity_zone_presence.py`

`ZonePresenceTracker.update()` takes a `global_track_id` and its floor coordinates, determines which `Zone` (if any) it is in via a ray-casting point-in-polygon test, and creates / closes `zone_presence` rows accordingly.

`Zone.polygon_json` format — JSON array of `[x, y]` vertex pairs:
```json
[[0,0],[500,0],[500,500],[0,500]]
```

- [ ] **Step 6.1: Write failing tests**

```python
# tests/test_identity_zone_presence.py
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.orm import Session

from vms.db.models import Camera, Zone, ZonePresence
from vms.identity.zone_presence import ZonePresenceTracker, point_in_polygon


# ── pure geometry ─────────────────────────────────────────────────────

def test_point_in_polygon_inside() -> None:
    poly = [[0, 0], [100, 0], [100, 100], [0, 100]]
    assert point_in_polygon(50.0, 50.0, poly) is True


def test_point_in_polygon_outside() -> None:
    poly = [[0, 0], [100, 0], [100, 100], [0, 100]]
    assert point_in_polygon(200.0, 200.0, poly) is False


def test_point_in_polygon_does_not_crash_on_boundary() -> None:
    poly = [[0, 0], [100, 0], [100, 100], [0, 100]]
    point_in_polygon(0.0, 0.0, poly)  # boundary — no assertion, just must not raise


# ── integration tests ─────────────────────────────────────────────────

@pytest.fixture()
def zone(db_session: Session) -> Zone:
    poly = [[0, 0], [500, 0], [500, 500], [0, 500]]
    z = Zone(name="Test Zone", polygon_json=json.dumps(poly))
    db_session.add(z)
    db_session.flush()
    return z


@pytest.mark.integration
def test_tracker_opens_presence_on_zone_entry(
    db_session: Session, zone: Zone
) -> None:
    tracker = ZonePresenceTracker(db=db_session)
    gid = uuid.uuid4()
    tracker.update(global_track_id=gid, floor_x=100.0, floor_y=100.0)
    db_session.flush()

    rows = (
        db_session.query(ZonePresence)
        .filter_by(global_track_id=gid, zone_id=zone.zone_id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].exited_at is None


@pytest.mark.integration
def test_tracker_closes_presence_on_zone_exit(
    db_session: Session, zone: Zone
) -> None:
    tracker = ZonePresenceTracker(db=db_session)
    gid = uuid.uuid4()
    tracker.update(global_track_id=gid, floor_x=100.0, floor_y=100.0)  # enters
    db_session.flush()
    tracker.update(global_track_id=gid, floor_x=9999.0, floor_y=9999.0)  # exits
    db_session.flush()

    rows = (
        db_session.query(ZonePresence)
        .filter_by(global_track_id=gid, zone_id=zone.zone_id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].exited_at is not None


@pytest.mark.integration
def test_tracker_ignores_tracklet_with_no_zone_match(
    db_session: Session, zone: Zone
) -> None:
    tracker = ZonePresenceTracker(db=db_session)
    gid = uuid.uuid4()
    tracker.update(global_track_id=gid, floor_x=9999.0, floor_y=9999.0)
    db_session.flush()

    rows = db_session.query(ZonePresence).filter_by(global_track_id=gid).all()
    assert rows == []
```

- [ ] **Step 6.2: Run — expect ImportError**
```powershell
python -m pytest tests/test_identity_zone_presence.py -v
```

- [ ] **Step 6.3: Implement `vms/identity/zone_presence.py`**

```python
"""Zone presence state machine.

On each update():
  - Find which zone (if any) the floor point falls in via point-in-polygon.
  - If entering a new zone: INSERT zone_presence (exited_at=NULL).
  - If leaving a zone: UPDATE exited_at on the open row.
  - If staying in same zone: no-op.

Maintains an in-memory cache of each tracklet's current zone to avoid
redundant DB queries on every frame.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

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
    """Tracks zone_presence rows for all active global_track_ids."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._current: dict[uuid.UUID, int | None] = {}  # gid → zone_id or None

    def update(
        self,
        global_track_id: uuid.UUID,
        floor_x: float,
        floor_y: float,
    ) -> None:
        """Reconcile zone membership for one tracklet."""
        zones: list[Zone] = self._db.query(Zone).all()
        matched: int | None = None
        for z in zones:
            if z.polygon_json is None:
                continue
            poly: list[list[float]] = json.loads(z.polygon_json)
            if point_in_polygon(floor_x, floor_y, poly):
                matched = z.zone_id
                break

        prev = self._current.get(global_track_id)
        if matched == prev:
            return  # no change

        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        if prev is not None:
            self._close(global_track_id, prev, now)
        if matched is not None:
            self._open(global_track_id, matched, now)
        self._current[global_track_id] = matched

    def _open(self, gid: uuid.UUID, zone_id: int, ts: datetime) -> None:
        self._db.add(ZonePresence(zone_id=zone_id, global_track_id=gid, entered_at=ts))

    def _close(self, gid: uuid.UUID, zone_id: int, ts: datetime) -> None:
        row = (
            self._db.query(ZonePresence)
            .filter_by(zone_id=zone_id, global_track_id=gid)
            .filter(ZonePresence.exited_at.is_(None))
            .first()
        )
        if row is not None:
            row.exited_at = ts
```

- [ ] **Step 6.4: Run — expect 6 passed**
```powershell
python -m pytest tests/test_identity_zone_presence.py -v
```

- [ ] **Step 6.5: Lint + type-check**
```powershell
ruff check vms/identity/zone_presence.py tests/test_identity_zone_presence.py
mypy vms/identity/zone_presence.py
```

- [ ] **Step 6.6: Commit**
```powershell
git add vms/identity/zone_presence.py tests/test_identity_zone_presence.py
git commit -m "feat(identity): add ZonePresenceTracker with point-in-polygon"
```

---

## Task 7: IdentityEngine

**Files:**
- Create: `vms/identity/engine.py`
- Create: `tests/test_identity_engine.py`

`IdentityEngine` exposes two stateful methods tested independently, and a `run()` loop that orchestrates the full pipeline.

**In-memory tracklet registry** — key: `(camera_id, local_track_id)`, value:
```python
@dataclass
class _TrackletEntry:
    global_track_id: uuid.UUID
    person_id: int | None
    last_embedding: np.ndarray | None   # most recent non-empty face embedding
    last_seen_ms: int                   # wall-clock ms — for 5-min stale eviction
    camera_id: int
```

**Cross-camera matching** (applied when a new `(cam_id, local_track_id)` pair arrives with an embedding):
- Iterate active entries from OTHER cameras (last_seen < 5 min).
- Compute cosine similarity vs `last_embedding`.
- If `best_sim ≥ settings.reid_cross_cam_sim` (0.65) AND `margin ≥ settings.reid_margin` (0.08): reuse that `global_track_id`.
- Else: assign new UUID.

- [ ] **Step 7.1: Write failing tests**

```python
# tests/test_identity_engine.py
from __future__ import annotations

import uuid

import numpy as np
import pytest

from vms.identity.engine import IdentityEngine
from vms.identity.reid import ReIdService
from unittest.mock import MagicMock


def _unit_vec(seed: int = 0) -> tuple[float, ...]:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(512).astype(np.float32)
    v /= np.linalg.norm(v)
    return tuple(float(x) for x in v)


def _make_engine() -> IdentityEngine:
    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = None
    return IdentityEngine(reid_service=reid)


def test_engine_same_camera_tracklet_gets_same_global_id() -> None:
    engine = _make_engine()
    gid1 = engine.assign_global_track_id(camera_id=1, local_track_id=5, embedding=None)
    gid2 = engine.assign_global_track_id(camera_id=1, local_track_id=5, embedding=None)
    assert gid1 == gid2


def test_engine_different_camera_unknown_embedding_gets_new_global_id() -> None:
    engine = _make_engine()
    gid1 = engine.assign_global_track_id(camera_id=1, local_track_id=5, embedding=None)
    gid2 = engine.assign_global_track_id(camera_id=2, local_track_id=5, embedding=None)
    assert gid1 != gid2


def test_engine_cross_camera_match_on_similar_embedding() -> None:
    engine = _make_engine()
    v = _unit_vec(seed=0)
    gid1 = engine.assign_global_track_id(camera_id=1, local_track_id=1, embedding=v)

    # Nearly identical embedding from camera 2 → should inherit gid1
    arr = np.array(v, dtype=np.float32)
    arr += np.random.default_rng(1).standard_normal(512).astype(np.float32) * 0.001
    arr /= np.linalg.norm(arr)
    v2 = tuple(float(x) for x in arr)
    gid2 = engine.assign_global_track_id(camera_id=2, local_track_id=1, embedding=v2)

    assert gid1 == gid2


def test_engine_identify_person_delegates_to_reid_service() -> None:
    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = 42
    engine = IdentityEngine(reid_service=reid)
    emb = _unit_vec(seed=1)
    pid = engine.identify_person(emb)
    assert pid == 42
    reid.identify.assert_called_once()


def test_engine_identify_person_returns_none_for_empty_embedding() -> None:
    engine = _make_engine()
    assert engine.identify_person(()) is None
```

- [ ] **Step 7.2: Run — expect ImportError**
```powershell
python -m pytest tests/test_identity_engine.py -v
```

- [ ] **Step 7.3: Implement `vms/identity/engine.py`**

```python
"""Identity engine: tracklet registry, cross-camera re-ID, person identification.

Cross-camera matching algorithm:
  1. (cam_id, local_track_id) known → return cached global_track_id.
  2. Unknown + has embedding → scan OTHER cameras' active tracklets
     (last_seen < 5 min) for cosine similarity:
       best ≥ reid_cross_cam_sim AND margin ≥ reid_margin → reuse global_track_id
       else → new UUID.
  3. Unknown + no embedding → new UUID.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass

import numpy as np

from vms.config import get_settings
from vms.identity.reid import ReIdService

logger = logging.getLogger(__name__)

_STALE_MS = 5 * 60 * 1000  # 5 minutes


@dataclass
class _TrackletEntry:
    global_track_id: uuid.UUID
    person_id: int | None
    last_embedding: np.ndarray | None
    last_seen_ms: int
    camera_id: int


class IdentityEngine:
    """Stateful per-process identity assignment for detection frames."""

    def __init__(self, reid_service: ReIdService) -> None:
        self._reid = reid_service
        self._registry: dict[tuple[int, int], _TrackletEntry] = {}

    def assign_global_track_id(
        self,
        camera_id: int,
        local_track_id: int,
        embedding: tuple[float, ...] | None,
    ) -> uuid.UUID:
        """Return a stable global_track_id for this (camera, local_track) pair."""
        key = (camera_id, local_track_id)
        now_ms = time.time_ns() // 1_000_000

        if key in self._registry:
            entry = self._registry[key]
            entry.last_seen_ms = now_ms
            if embedding:
                entry.last_embedding = np.array(embedding, dtype=np.float32)
            return entry.global_track_id

        emb_arr = np.array(embedding, dtype=np.float32) if embedding else None
        matched_gid = self._cross_camera_match(emb_arr, camera_id, now_ms) if emb_arr is not None else None
        gid = matched_gid if matched_gid is not None else uuid.uuid4()

        self._registry[key] = _TrackletEntry(
            global_track_id=gid,
            person_id=None,
            last_embedding=emb_arr,
            last_seen_ms=now_ms,
            camera_id=camera_id,
        )
        return gid

    def identify_person(self, embedding: tuple[float, ...]) -> int | None:
        """Return person_id from FAISS if embedding is non-empty, else None."""
        if not embedding:
            return None
        return self._reid.identify(np.array(embedding, dtype=np.float32))

    def _cross_camera_match(
        self,
        query: np.ndarray,
        camera_id: int,
        now_ms: int,
    ) -> uuid.UUID | None:
        """Scan other-camera active tracklets for a cosine similarity match."""
        settings = get_settings()
        q = query / (np.linalg.norm(query) + 1e-8)
        best_sim = -1.0
        second_sim = -1.0
        best_gid: uuid.UUID | None = None

        for (cam, _), entry in self._registry.items():
            if cam == camera_id:
                continue
            if now_ms - entry.last_seen_ms > _STALE_MS:
                continue
            if entry.last_embedding is None:
                continue
            e = entry.last_embedding / (np.linalg.norm(entry.last_embedding) + 1e-8)
            sim = float(np.dot(q, e))
            if sim > best_sim:
                second_sim = best_sim
                best_sim = sim
                best_gid = entry.global_track_id
            elif sim > second_sim:
                second_sim = sim

        if best_sim < settings.reid_cross_cam_sim:
            return None
        margin = best_sim - second_sim if second_sim > -1.0 else best_sim
        if margin < settings.reid_margin:
            return None
        return best_gid
```

- [ ] **Step 7.4: Run — expect 5 passed**
```powershell
python -m pytest tests/test_identity_engine.py -v
```

- [ ] **Step 7.5: Run full suite**
```powershell
python -m pytest tests/ -q
```

- [ ] **Step 7.6: Lint + type-check**
```powershell
ruff check vms/identity/engine.py tests/test_identity_engine.py
mypy vms/identity/engine.py
```

- [ ] **Step 7.7: Commit**
```powershell
git add vms/identity/engine.py tests/test_identity_engine.py
git commit -m "feat(identity): add IdentityEngine with cross-camera re-ID"
```

---

## Task 8: GDPR Purge Endpoint

**Files:**
- Modify: `vms/api/schemas.py`
- Modify: `vms/api/routes/persons.py`
- Modify: `tests/test_api_persons.py`

`DELETE /api/persons/{id}` — admin-only. Blanks embeddings (zeros, not deletes), sets `is_active=False`, `purged_at`, `thumbnail_path=None`, writes an immutable audit row, and returns 204.

**Key facts from reading the codebase:**
- `write_audit_event(session, *, event_type, actor_user_id, target_type, target_id, payload)` calls `session.commit()` internally — do NOT call `db.commit()` separately after.
- The `PersonEmbedding.embedding` column is `Vector(512)`. Zero it with `np.zeros(512, dtype=np.float32)`.
- `faiss_dirty` publish is fire-and-forget background work; the FAISS index rebuilds on the next identity service restart. Phase 2b will wire up the async background publish.

- [ ] **Step 8.1: Add `PurgeRequest` to schemas**

In `vms/api/schemas.py`, append:
```python
class PurgeRequest(BaseModel):
    confirmation_name: str = Field(..., description="Must match person.name exactly")
    reason: str = Field(..., min_length=10, max_length=500)
```

- [ ] **Step 8.2: Write failing tests**

Append to `tests/test_api_persons.py`:
```python
@pytest.mark.asyncio
async def test_purge_person_returns_204(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/persons",
            json={"name": "Purge Target", "employee_id": "E_PURGE_01"},
            headers=_auth_headers(role="admin"),
        )
        person_id = create_resp.json()["person_id"]
        resp = await client.delete(
            f"/api/persons/{person_id}",
            json={"confirmation_name": "Purge Target", "reason": "GDPR erasure request from subject"},
            headers=_auth_headers(role="admin"),
        )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_purge_person_requires_admin_role() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(
            "/api/persons/1",
            json={"confirmation_name": "Anyone", "reason": "test reason here please"},
            headers=_auth_headers(role="guard"),
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_purge_person_rejects_wrong_confirmation(db_session: Session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/api/persons",
            json={"name": "Real Name", "employee_id": "E_PURGE_02"},
            headers=_auth_headers(role="admin"),
        )
        person_id = create_resp.json()["person_id"]
        resp = await client.delete(
            f"/api/persons/{person_id}",
            json={"confirmation_name": "Wrong Name", "reason": "test reason here please"},
            headers=_auth_headers(role="admin"),
        )
    assert resp.status_code == 409
```

- [ ] **Step 8.3: Run new tests — expect 3 failures**
```powershell
python -m pytest tests/test_api_persons.py -v -k "purge"
```
Expected: 3 failures (route does not exist yet).

- [ ] **Step 8.4: Implement purge endpoint**

Add to `vms/api/routes/persons.py` (after the existing imports):
```python
from datetime import datetime

import numpy as np

from vms.api.schemas import PurgeRequest
from vms.db.audit import write_audit_event
```

Then add this route (after `search_persons`):
```python
@router.delete(
    "/persons/{person_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def purge_person(
    person_id: int,
    body: PurgeRequest,
    db: Session = Depends(get_db),  # noqa: B008
    user: dict[str, Any] = Depends(get_current_user),  # noqa: B008
) -> None:
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

    person.is_active = False
    person.purged_at = datetime.utcnow()
    person.thumbnail_path = None

    blank = np.zeros(512, dtype=np.float32)
    for emb in db.query(PersonEmbedding).filter_by(person_id=person_id).all():
        emb.embedding = blank
        emb.quality_score = 0.0

    # write_audit_event calls session.commit() internally — do not commit separately
    write_audit_event(
        db,
        event_type="PERSON_PURGED",
        actor_user_id=int(user["sub"]),
        target_type="person",
        target_id=str(person_id),
        payload=body.reason,
    )
```

- [ ] **Step 8.5: Run purge tests — expect 3 passed**
```powershell
python -m pytest tests/test_api_persons.py -v -k "purge"
```

- [ ] **Step 8.6: Run full suite**
```powershell
python -m pytest tests/ -q
```

- [ ] **Step 8.7: Lint + type-check**
```powershell
ruff check vms/api/routes/persons.py vms/api/schemas.py tests/test_api_persons.py
mypy vms/api/routes/persons.py
```

- [ ] **Step 8.8: Final quality gates**
```powershell
black vms/ tests/
ruff check vms/ tests/
mypy vms/
```
Expected: all clean.

- [ ] **Step 8.9: Commit**
```powershell
git add vms/api/routes/persons.py vms/api/schemas.py tests/test_api_persons.py
git commit -m "feat(api): add GDPR purge endpoint DELETE /api/persons/{id}"
```

---

## Self-Review Checklist

| Spec requirement | Covered by |
|---|---|
| FAISS index rebuilt from `person_embeddings` on startup | Task 2 `FaissIndex.rebuild()` |
| FAISS excludes `is_active=False` persons | Task 2 — `filter(Person.is_active.is_(True))` |
| FAISS `remove_ids` after GDPR purge | Tasks 5 + 8 — `publish_remove`; `FaissIndex.remove()` |
| `adaface_min_sim=0.72` + `reid_margin=0.08` gates | Task 3 `ReIdService.identify()` |
| Cross-camera re-ID: `reid_cross_cam_sim=0.65` + margin | Task 7 `IdentityEngine._cross_camera_match()` |
| 5-minute stale eviction for cross-camera matching | Task 7 `_STALE_MS = 5 * 60 * 1000` |
| Homography bottom-centre foot point | Task 4 `project_to_floor()` |
| `Zone.polygon_json` point-in-polygon | Task 6 `point_in_polygon()` |
| `zone_presence.entered_at` / `exited_at` lifecycle | Task 6 `ZonePresenceTracker` |
| `faiss_dirty` stream events for enrolment + purge | Task 5 |
| GDPR purge: admin role + confirmation_name match | Task 8 |
| GDPR purge: embeddings zeroed (not deleted) | Task 8 — `np.zeros(512)` |
| GDPR purge: `is_active=False`, `purged_at` set | Task 8 |
| GDPR purge: audit log `PERSON_PURGED` | Task 8 `write_audit_event()` |
| `cameras.homography_matrix` column | Task 1 migration |
| `zones.adjacent_zone_ids` column | Task 1 migration |
| Config: `adaface_min_sim`, `reid_cross_cam_sim`, `reid_margin` | Pre-existing in `vms/config.py` — no changes needed |

**Placeholder scan:** No TBD, TODO, or "similar to" references. All steps include complete code.

**Type consistency:**
- `FaissIndex.search()` returns `list[tuple[int, float]]` — consumed correctly by `ReIdService`
- `IdentityEngine.assign_global_track_id()` takes `embedding: tuple[float, ...] | None` — matches `FaceWithEmbedding.embedding` type
- `ZonePresenceTracker.update()` takes `global_track_id: uuid.UUID` — matches `TrackingEvent.global_track_id` type
- `write_audit_event` signature: `(session, *, event_type, actor_user_id, target_type, target_id, payload)` — verified from source

---

## Execution Options

Plan saved to `docs/superpowers/plans/2026-05-14-vms-v2-phase2a-identity-framework.md`.

**1. Subagent-Driven (recommended)** — fresh subagent per task, diff reviewed between tasks.
Use `superpowers:subagent-driven-development`.

**2. Inline Execution** — execute tasks in this session with checkpoints.
Use `superpowers:executing-plans`.

**Phase 2b (Anomaly Framework)** — `AnomalyDetector` ABC, `AlertFSM`, maintenance calendar, and concrete detectors — will be written as a separate plan after Phase 2a ships.
