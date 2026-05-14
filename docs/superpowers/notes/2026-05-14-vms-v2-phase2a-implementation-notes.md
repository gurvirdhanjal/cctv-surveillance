# VMS v2 Phase 2a — Implementation Notes

**Phase:** 2a — Identity Framework
**Plan:** `docs/superpowers/plans/2026-05-14-vms-v2-phase2a-identity-framework.md`
**Branch:** `feat/phase-1b-ingestion-inference-api`

---

## Pre-flight

- `faiss-cpu==1.8.0` was already in `requirements.txt`. No install needed.
- 96 tests passing at start.

---

## Task 1: Schema Migration — COMPLETE

**Commit:** `eff370b`
**Files:** `vms/db/models.py`, `alembic/versions/5b4fe0f76497_phase2a_add_homography_adjacent_zones.py`

### Decisions

- `Camera.homography_matrix` — `Text`, nullable. Stores a 3×3 row-major float64 matrix as a JSON string (9 floats).
- `Zone.adjacent_zone_ids` — `Text`, nullable. Stores a JSON array of integer zone_ids.
- Both columns placed immediately after the last existing column in each class.

### No issues

Round-trip (`upgrade → downgrade -1 → upgrade`) clean. 96 tests still passing.

---

## Task 2: FaissIndex — COMPLETE

**Commit:** `c9fdb46`
**Files:** `vms/identity/__init__.py`, `vms/identity/faiss_index.py`, `tests/test_identity_faiss_index.py`

### Decisions

- `IndexIDMap2(IndexFlatIP(512))` — inner product after L2 normalisation equals cosine similarity.
- `_emb_to_person: dict[int, int]` — in-memory map from `embedding_id` to `person_id` for O(1) lookup after FAISS search.
- `add()` normalises before insertion; `search()` normalises the query.

### Fixes applied

- `import faiss` → `# type: ignore[import-untyped]` — faiss has no type stubs.
- `np.ndarray` type args required for mypy strict: `np.ndarray[Any, Any]`.
- `test_faiss_index_rebuild_excludes_inactive_persons` assertion changed from `idx.count() == 0` to `person.person_id not in {pid for pid, _ in idx.search(..., k=10)}` — the stricter assertion breaks when other tests commit active persons to the DB before this test runs (API tests commit via FastAPI's `get_db` session, not the rolled-back `db_session` fixture).

---

## Task 3: ReIdService — COMPLETE

**Commit:** `b503be2`
**Files:** `vms/identity/reid.py`, `tests/test_identity_reid.py`

### Decisions

- `k=2` passed to `FaissIndex.search()` — need two results to compute the margin gate.
- Margin gate skipped when only one result exists (no second competitor = unambiguous match).
- Thresholds read from `get_settings()` on every call — no per-instance caching. Enables hot-reload of settings in tests.

---

## Task 4: Homography Projection — COMPLETE

**Commit:** `a7738d9`
**Files:** `vms/identity/homography.py`, `tests/test_identity_homography.py`

### Decisions

- Bottom-centre foot point `((x1+x2)/2, y2)` used instead of centroid — more accurate for standing persons because the foot position is invariant to crouch/lean.
- `cv2.perspectiveTransform` requires float32 input; `H` cast to `float32` for the cv2 call.
- Return type `np.ndarray | None` with `# type: ignore[type-arg]` on the `np.ndarray` (mypy doesn't flag this for return types).

---

## Task 5: faiss_dirty Stream Events — COMPLETE

**Commit:** `4e6e5a4`
**Files:** `vms/identity/faiss_dirty.py`, `tests/test_identity_faiss_dirty.py`

### Decisions

- `_STREAM = "faiss_dirty"` — matches the stream name referenced in the spec and FAISS consistency §15.
- `publish_remove` JSON-serialises `embedding_ids` list so the consumer can process bulk removes atomically.
- `aioredis.Redis` used without `type: ignore` — consistent with rest of codebase (redis-py stubs handle it).

### Fixes applied

- `type: ignore[type-arg]` on `aioredis.Redis` was initially added but mypy flagged it as unused (`unused-ignore`). Removed — consistent with `vms/redis_client.py` and other files.

---

## Task 6: ZonePresenceTracker — COMPLETE

**Commit:** `933cfbb`
**Files:** `vms/identity/zone_presence.py`, `tests/test_identity_zone_presence.py`

### Decisions

- Ray-casting point-in-polygon test — standard O(n) algorithm; sufficient for <50 vertices per zone.
- In-memory `_current: dict[uuid.UUID, int | None]` — tracks each tracklet's current zone_id so we avoid a DB query on every frame for the no-change case.
- `datetime.now(tz=timezone.utc).replace(tzinfo=None)` — strips timezone for `TIMESTAMP WITHOUT TIME ZONE` columns (same pattern as Phase 1B DB writer).
- `_open` / `_close` helpers keep `update()` readable.

---

## Task 7: IdentityEngine — COMPLETE

**Commit:** `cd87a1b`
**Files:** `vms/identity/engine.py`, `tests/test_identity_engine.py`

### Decisions

- `_STALE_MS = 5 * 60 * 1000` — 5 minutes in milliseconds, matching spec v1 §7.
- `1e-8` epsilon in cosine normalisation prevents division by zero on zero vectors.
- `second_sim` initialised to `-1.0` (not `0.0`) so a single-candidate margin check uses `best_sim - (-1.0) = best_sim + 1.0`, which is always ≥ 0.08. This correctly skips the margin gate when there's no competitor.
- `_TrackletEntry` is a plain `@dataclass` (not frozen) — it's mutated in-place on `last_seen_ms` and `last_embedding` updates.

### Fixes applied

- `pytest` and `uuid` unused imports in test file — removed by ruff.

---

## Task 8: GDPR Purge Endpoint — COMPLETE

**Commit:** `634c8c4`
**Files:** `vms/api/routes/persons.py`, `vms/api/schemas.py`, `tests/test_api_persons.py`, `tests/test_db_audit.py`

### Decisions

- **`status_code=204` on router decorator disallowed with request body in FastAPI 0.111.0**: Assertion `is_body_allowed_for_status_code(204)` fires at app load time. Fix: remove `status_code=204` from decorator, change return type to `Response`, return `Response(status_code=204)` explicitly.
- **`httpx.AsyncClient.delete()` does not accept `json=`**: DELETE requests with a JSON body must use `client.request("DELETE", url, json=...)`.
- **`actor_user_id` FK guard**: JWT `sub` may not correspond to a real DB user (e.g., test JWTs, deleted users). Endpoint checks `db.get(DBUser, actor_id)` and passes `None` if not found — still records the purge event without losing it on FK violation.
- **`emb.embedding = blank` mypy error**: `PersonEmbedding.embedding` is `Mapped[list[float]]`. Assigning `np.ndarray` triggers mypy incompatible-types. Fix: `blank: list[float] = np.zeros(512, dtype=np.float32).tolist()`.
- **Audit chain test isolation**: `test_first_row_uses_zero_prev_hash` and `test_chain_integrity_across_three_rows` assumed an empty `audit_log` table. The purge tests commit `PERSON_PURGED` rows via FastAPI's `get_db` (a non-rolled-back session), which broke the "prev_hash == _ZERO_HASH" assumption when run in the full suite. Fixed by using a `_last_hash()` helper that reads the actual last row before writing, making both tests order-independent.

---

## Phase 2a final quality gates

| Check | Result |
|---|---|
| `pytest tests/ -q` | 128 passed |
| `ruff check vms/ tests/` | Clean |
| `black vms/ tests/` | Clean |
| `mypy vms/` | Clean (no errors) |
| `print()` in vms/ | None |
| Hard-coded thresholds | None — all use `get_settings()` |
| ONNX files committed | None |

---

## Running state

| Task | Status | Commit | New Tests |
|------|--------|--------|-----------|
| Pre-flight | DONE | — | — |
| Task 1: Schema Migration | DONE | `eff370b` | 0 |
| Task 2: FaissIndex | DONE | `c9fdb46` | +7 |
| Task 3: ReIdService | DONE | `b503be2` | +5 |
| Task 4: Homography | DONE | `a7738d9` | +4 |
| Task 5: faiss_dirty | DONE | `4e6e5a4` | +2 |
| Task 6: ZonePresenceTracker | DONE | `933cfbb` | +6 |
| Task 7: IdentityEngine | DONE | `cd87a1b` | +5 |
| Task 8: GDPR Purge | DONE | `634c8c4` | +3 |
| **Final total** | | | **128** |
