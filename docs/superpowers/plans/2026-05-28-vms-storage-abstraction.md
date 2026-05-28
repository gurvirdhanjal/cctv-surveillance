# VMS Storage Abstraction Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: NOT STARTED**

**Goal:** Introduce a `StorageBackend` Protocol with `LocalStorageBackend` and `MinIOStorageBackend` implementations. Wire GDPR purge and thumbnail/snapshot writes to use the abstraction. Store relative keys in DB instead of absolute paths.

**Architecture:** New `vms/storage/` package. `get_storage()` singleton (like `get_settings()`). Two Alembic migrations: one for schema (path → key semantics, no DDL change), one for data (convert existing absolute paths). GDPR purge and enrolment routes updated.

**Tech Stack:** `boto3` for MinIO (already S3-compatible), `pathlib` for local, `pydantic-settings` for config, `pytest` + `tmp_path` fixture for tests.

**Spec refs:** `docs/superpowers/specs/2026-05-28-vms-storage-scalability.md` §§ 1.1–1.11

---

## Task 1 — StorageBackend Protocol + generate_key helper

- [ ] 1.1 Create `vms/storage/__init__.py` (empty)
- [ ] 1.2 Create `vms/storage/backends.py`:
  - `StorageBackend` Protocol (runtime_checkable) with `write/read/delete/exists/url`
  - `generate_key(prefix: str, ext: str = "jpg") -> str` — returns `"{prefix}/{YYYY}/{MM}/{DD}/{uuid4}.{ext}"` using UTC date
- [ ] 1.3 Write `tests/test_storage_backends.py` — unit tests for `generate_key`:
  - Key matches pattern `^[a-z]+/\d{4}/\d{2}/\d{2}/[0-9a-f-]{36}\.jpg$`
  - `thumbnails/` prefix used for thumbnails, `snapshots/` for clips
  - Two successive calls return different UUIDs
- [ ] 1.4 RED → run tests → confirm they fail
- [ ] 1.5 Implement `generate_key` → GREEN

---

## Task 2 — LocalStorageBackend

- [ ] 2.1 Add `LocalStorageBackend` class to `vms/storage/backends.py`:
  - `__init__(self, base_dir: str) -> None` — stores `pathlib.Path(base_dir)`
  - `write(key, data)` — creates parents, writes bytes
  - `read(key)` → bytes
  - `delete(key)` → `unlink(missing_ok=True)`
  - `exists(key)` → bool
  - `url(key)` → `f"/media/{key}"`
- [ ] 2.2 Verify `isinstance(LocalStorageBackend(...), StorageBackend)` — Protocol runtime check
- [ ] 2.3 Write tests in `tests/test_storage_backends.py` using `tmp_path` fixture:
  - `test_local_write_creates_directories` — writes a key with nested path; checks file exists
  - `test_local_read_returns_bytes` — write then read returns same bytes
  - `test_local_delete_removes_file` — write, delete, exists returns False
  - `test_local_delete_missing_key_is_noop` — delete non-existent key does not raise
  - `test_local_exists_returns_false_for_missing` — baseline
  - `test_local_url_format` — returns `/media/{key}`
- [ ] 2.4 RED → GREEN → pass

---

## Task 3 — Config additions

- [ ] 3.1 Add to `vms/config.py`:
  ```python
  storage_backend: str = "local"
  storage_local_dir: str = "thumbnails"
  minio_endpoint: str = ""
  minio_access_key: str = ""
  minio_secret_key: str = ""
  minio_bucket: str = "vms-media"
  ```
- [ ] 3.2 Write `tests/test_config.py` (add test or new file):
  - `test_storage_backend_defaults_to_local` — default is `"local"`
  - `test_storage_local_dir_defaults` — default is `"thumbnails"`
  - `test_minio_settings_default_empty` — endpoint/key/secret default to `""`
- [ ] 3.3 RED → GREEN → pass

---

## Task 4 — get_storage() factory

- [ ] 4.1 Create `vms/storage/factory.py`:
  - `get_storage() -> StorageBackend` — `lru_cache(maxsize=1)`; returns `LocalStorageBackend` when `storage_backend == "local"`, raises `ValueError` for unknown backends
  - `clear_storage_cache() -> None` — calls `get_storage.cache_clear()`; needed in tests
- [ ] 4.2 Write tests in `tests/test_storage_factory.py`:
  - `test_get_storage_returns_local_backend_by_default` — patch settings, check isinstance
  - `test_get_storage_raises_for_unknown_backend` — set `storage_backend="invalid"`, expect `ValueError`
  - `test_clear_storage_cache` — call twice, confirm singleton; clear, confirm new instance
- [ ] 4.3 RED → GREEN → pass

---

## Task 5 — MinIOStorageBackend

- [ ] 5.1 Add `MinIOStorageBackend` class to `vms/storage/backends.py`:
  - `__init__(self, endpoint, access_key, secret_key, bucket) -> None` — lazy `boto3.client` construction
  - `write/read/delete/exists/url` as described in spec §1.4
  - `_ensure_bucket()` — `create_bucket` if not exists (called in `__init__`)
- [ ] 5.2 Update `factory.py` — handle `storage_backend == "minio"` case
- [ ] 5.3 Write `tests/test_storage_minio.py` using `moto` (S3 mock):
  - `test_minio_write_and_read` — write bytes, read back, assert equal
  - `test_minio_delete_removes_object` — write, delete, exists returns False
  - `test_minio_delete_missing_is_noop` — delete non-existent key does not raise
  - `test_minio_exists_false_for_missing` — baseline
  - `test_minio_url_is_presigned` — url() returns a non-empty string containing the key
  - `test_minio_bucket_auto_created` — new MinIOStorageBackend without pre-existing bucket succeeds
- [ ] 5.4 Add `moto[s3]` to `pyproject.toml` dev dependencies
- [ ] 5.5 RED → GREEN → pass

---

## Task 6 — Alembic migration: path → key semantics

The DB columns `persons.thumbnail_path` and `person_clip_embeddings.snapshot_path` remain `String(500)` — no DDL change. The migration adds a comment documenting the semantic change and includes a data migration that converts any existing absolute paths to relative keys.

- [ ] 6.1 Generate migration: `alembic revision -m "storage_key_semantics_thumbnail_and_snapshot_paths"`
- [ ] 6.2 Write `upgrade()`:
  ```python
  # Data migration: strip absolute path prefix from existing rows
  # Only affects rows where path starts with os.sep (absolute path)
  # Pattern: remove everything up to and including 'thumbnails/' prefix
  op.execute("""
      UPDATE persons
      SET thumbnail_path = SUBSTRING(thumbnail_path FROM POSITION('thumbnails/' IN thumbnail_path))
      WHERE thumbnail_path IS NOT NULL AND thumbnail_path NOT LIKE 'thumbnails/%'
        AND thumbnail_path NOT LIKE 'snapshots/%'
  """)
  op.execute("""
      UPDATE person_clip_embeddings
      SET snapshot_path = SUBSTRING(snapshot_path FROM POSITION('snapshots/' IN snapshot_path))
      WHERE snapshot_path NOT LIKE 'thumbnails/%'
        AND snapshot_path NOT LIKE 'snapshots/%'
  """)
  ```
- [ ] 6.3 Write `downgrade()` — no-op (data migration is irreversible; keys remain valid in both directions)
- [ ] 6.4 Run `alembic upgrade head` locally; confirm no errors
- [ ] 6.5 Run `alembic downgrade -1` then `alembic upgrade head` — round-trip clean

---

## Task 7 — Wire GDPR purge to storage backend

- [ ] 7.1 Update `vms/api/routes/persons.py`:
  - Import `get_storage` from `vms.storage.factory`
  - Replace `pathlib.Path(thumbnail_path).unlink(missing_ok=True)` with `storage.delete(thumbnail_key)` (call `get_storage()` at top of function)
  - Replace `pathlib.Path(snap).unlink(missing_ok=True)` with `storage.delete(snap_key)`
  - Variable rename: `thumbnail_path` → `thumbnail_key`, `clip_paths` → `clip_keys` where these refer to DB values
- [ ] 7.2 Write/update `tests/test_api_persons.py`:
  - `test_purge_calls_storage_delete_for_thumbnail` — mock `get_storage`, assert `delete(key)` called with the thumbnail key
  - `test_purge_calls_storage_delete_for_clip_snapshots` — same for clip snapshots
  - `test_purge_with_no_thumbnail_does_not_call_delete` — when `thumbnail_key` is None
  - Existing purge tests must still pass
- [ ] 7.3 RED → GREEN → pass
- [ ] 7.4 `ruff check vms/ tests/` + `black vms/ tests/` + `mypy vms/` — clean

---

## Task 8 — Wire thumbnail write in enrolment

When `POST /api/persons/{id}/embeddings` accepts an image file (Phase 4 feature), it will write the thumbnail via `get_storage().write(key, data)`. Currently the endpoint doesn't write thumbnails (it stores vector embeddings only). This task creates the helper so Phase 4 can call it.

- [ ] 8.1 Create `vms/storage/media.py`:
  - `write_thumbnail(person_id: int, data: bytes, storage: StorageBackend) -> str` — calls `generate_key("thumbnails")`, writes data, returns key
  - `write_snapshot(camera_id: int, data: bytes, storage: StorageBackend) -> str` — same with `"snapshots"` prefix
- [ ] 8.2 Write `tests/test_storage_media.py`:
  - `test_write_thumbnail_returns_key_with_thumbnails_prefix`
  - `test_write_snapshot_returns_key_with_snapshots_prefix`
  - `test_write_thumbnail_key_stored_via_backend` — mock backend, assert `write` called
- [ ] 8.3 RED → GREEN → pass

---

## Task 9 — Static media mount for local backend

- [ ] 9.1 In `vms/api/main.py`, after app creation, mount static files when `storage_backend == "local"`:
  ```python
  if get_settings().storage_backend == "local":
      from fastapi.staticfiles import StaticFiles
      app.mount("/media", StaticFiles(directory=get_settings().storage_local_dir, html=False), name="media")
  ```
  Guard behind `pathlib.Path(dir).exists()` — skip if directory not yet created.
- [ ] 9.2 Write test `tests/test_api_main.py`:
  - `test_media_route_mounted_for_local_backend` — GET `/media/` returns 404 (no index) not 404 from missing mount
  - `test_media_route_not_mounted_for_minio_backend` — when `storage_backend=minio`, no `/media` route
- [ ] 9.3 RED → GREEN → pass

---

## Task 10 — Full test suite verification

- [ ] 10.1 `pytest` — all tests pass (target: ≥ 176 existing + new storage tests)
- [ ] 10.2 `pytest --cov=vms/storage --cov-report=term-missing` — ≥ 90% coverage on `vms/storage/`
- [ ] 10.3 `ruff check vms/ tests/` — clean
- [ ] 10.4 `black vms/ tests/` — no changes
- [ ] 10.5 `mypy vms/` — clean (no new errors)
- [ ] 10.6 Update this plan: mark all tasks `[x]`, set `**Status: COMPLETE**`
- [ ] 10.7 Update `CLAUDE.md §3` — note Storage Abstraction complete with commit hash

---

## Acceptance Criteria

- `get_storage()` returns `LocalStorageBackend` by default with no env vars set
- GDPR purge no longer imports `pathlib` for file deletion
- `write_thumbnail` and `write_snapshot` helpers exist and are covered by tests
- All 10 tasks above checked; all tests green; mypy clean
- `moto` is listed in dev dependencies; `boto3` in production dependencies
