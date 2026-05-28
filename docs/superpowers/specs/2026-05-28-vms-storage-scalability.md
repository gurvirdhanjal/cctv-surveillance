# VMS Storage Scalability
**Design Specification** · 2026-05-28
**Status:** Approved

This spec covers two independent but related scalability changes:

1. **Storage Abstraction Layer** — decouple file I/O from `pathlib` so the system can switch between local disk and MinIO (S3-compatible object storage) via config, enabling horizontal scaling.
2. **`tracking_events` Time-Range Partitioning** — partition the highest-write table by month so that old data can be dropped instantly (no `DELETE`) and query planner can skip entire partitions for time-bounded queries.

Both changes are prerequisite to Tier 2+ scaling (>200 cameras, multi-server). Neither breaks the Phase 2b anomaly framework.

---

## Part 1: Storage Abstraction Layer

### 1.1 Motivation

The current codebase writes/deletes thumbnails and CLIP snapshots with `pathlib.Path` directly in `vms/api/routes/persons.py`. This hardcodes the assumption of a single local filesystem. Three problems:

1. **GDPR purge** calls `pathlib.Path(path).unlink(missing_ok=True)` — breaks on any non-local backend.
2. **Phase 5 at-rest encryption** states face thumbnails must be on an encrypted volume. Using a MinIO volume mounted with dm-crypt is simpler than managing per-file encryption.
3. **Horizontal scaling**: a second application server can't reach `/thumbnails/` on the first server's local disk. Shared object storage is the standard answer.

### 1.2 `StorageBackend` Protocol

```python
# vms/storage/backends.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class StorageBackend(Protocol):
    def write(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def url(self, key: str) -> str: ...
```

`key` is always a **relative path** (e.g., `thumbnails/2026/05/28/abc123.jpg`).  
`url()` returns a usable URL for an HTTP client — either a static-serve path or a presigned S3 URL.

### 1.3 `LocalStorageBackend`

- `base_dir` from `VMS_STORAGE_LOCAL_DIR` (default: `"thumbnails"`).
- `write()` creates parent directories if absent.
- `url(key)` returns `"/media/{key}"` — FastAPI mounts `StaticFiles` at `/media` on the configured dir.
- `delete()` calls `pathlib.Path.unlink(missing_ok=True)` — silently no-ops on missing keys.

### 1.4 `MinIOStorageBackend`

Uses `boto3` with `endpoint_url` set to the MinIO address (S3-compatible API).

- `write()` → `put_object`
- `read()` → `get_object`
- `delete()` → `delete_object` (swallow `ClientError` for missing keys)
- `exists()` → `head_object` (catch `ClientError` → `False`)
- `url()` → `generate_presigned_url("get_object", ExpiresIn=3600)`

Bucket auto-created on first startup if it doesn't exist (`create_bucket` with a check).

### 1.5 Key Format

Keys follow a date-partitioned layout to keep directory sizes manageable:

```
thumbnails/{YYYY}/{MM}/{DD}/{uuid4}.jpg     # persons.thumbnail_path
snapshots/{YYYY}/{MM}/{DD}/{uuid4}.jpg      # person_clip_embeddings.snapshot_path
```

Date component is the wall-clock UTC date at write time. Extension is always `.jpg`.

### 1.6 Factory and Singleton

```python
# vms/storage/factory.py
from functools import lru_cache
from vms.storage.backends import StorageBackend

@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    settings = get_settings()
    if settings.storage_backend == "minio":
        return MinIOStorageBackend(...)
    return LocalStorageBackend(settings.storage_local_dir)
```

FastAPI routes use `Depends(get_storage)`. Non-FastAPI callers (GDPR purge helper) call `get_storage()` directly.

### 1.7 Config Additions

Add to `vms/config.py`:

```python
storage_backend: str = "local"          # VMS_STORAGE_BACKEND — "local" | "minio"
storage_local_dir: str = "thumbnails"   # VMS_STORAGE_LOCAL_DIR
minio_endpoint: str = ""                # VMS_MINIO_ENDPOINT  e.g. "http://minio:9000"
minio_access_key: str = ""              # VMS_MINIO_ACCESS_KEY
minio_secret_key: str = ""             # VMS_MINIO_SECRET_KEY
minio_bucket: str = "vms-media"         # VMS_MINIO_BUCKET
```

`minio_*` settings are only read when `storage_backend == "minio"`.

### 1.8 DB Column Semantics Change

| Column | Before | After |
|---|---|---|
| `persons.thumbnail_path` | Absolute filesystem path | Relative storage key |
| `person_clip_embeddings.snapshot_path` | Absolute filesystem path | Relative storage key |

Both columns remain `String(500)`. NULL in `thumbnail_path` means no thumbnail (unchanged).

The Alembic migration includes a data migration that converts any existing absolute paths to relative keys by stripping the configured `storage_local_dir` prefix.

### 1.9 GDPR Purge Integration

In `vms/api/routes/persons.py`, the two file-delete blocks become:

```python
storage = get_storage()
if thumbnail_key and storage.exists(thumbnail_key):
    storage.delete(thumbnail_key)
for key in clip_keys:
    storage.delete(key)
```

The `delete()` method is idempotent (no-op on missing keys), so the `if exists` check on thumbnail is optional but kept as a guard against spurious log entries.

### 1.10 Static Media Serving

For `LocalStorageBackend`, add to `vms/api/main.py`:

```python
from fastapi.staticfiles import StaticFiles
app.mount("/media", StaticFiles(directory=get_settings().storage_local_dir), name="media")
```

This is skipped (or replaced with a presigned-URL redirect) when `storage_backend == "minio"`.

### 1.11 Scope Boundary

This spec covers thumbnail and snapshot storage only. `models/` directory (ONNX weights) is out of scope — managed by `vms-models` manifest. Audit log is DB-only, out of scope.

---

## Part 2: `tracking_events` Time-Range Partitioning

### 2.1 Capacity Analysis

| Metric | Value |
|---|---|
| Cameras (v1) | 52 |
| Frame rate | 25 fps |
| Rows/second | ~1,300 |
| Rows/day | ~112M |
| Rows/month | ~3.4B |
| Default retention (Phase 5) | 90 days |
| Total rows at retention ceiling | ~10B |

PostgreSQL table bloat, autovacuum cost, and query planner decisions all degrade non-linearly past ~100M rows on a single heap. Monthly partitions reduce the working set to ~3.4B rows per partition and allow old data to be dropped via `DROP TABLE` (O(1)) rather than `DELETE` (O(rows)).

### 2.2 Partition Strategy

- **Method:** `PARTITION BY RANGE (event_ts)`
- **Granularity:** Monthly (each partition covers `[month_start, next_month_start)`)
- **Naming convention:** `tracking_events_y{YYYY}m{MM}` (e.g., `tracking_events_y2026m05`)
- **DEFAULT partition:** Required. Events with `event_ts` outside any defined range go to DEFAULT. Prevents write errors during missed partition creation. DEFAULT partition is monitored and reconciled in `PartitionManager`.

### 2.3 Primary Key Change

PostgreSQL requires that **every unique constraint on a partitioned table includes the partition key column**. The existing `uq_tracking_idem(camera_id, local_track_id, event_ts)` already includes `event_ts` — no change needed there.

The PK must also include `event_ts`:

| | Before | After |
|---|---|---|
| PK | `(event_id)` | `(event_id, event_ts)` |
| Unique | `(camera_id, local_track_id, event_ts)` | unchanged |

`event_id` is still `BIGSERIAL` (sequence-backed autoincrement). The composite PK `(event_id, event_ts)` does **not** mean `event_id` is non-unique globally — the sequence guarantees that. The PK's `event_ts` component is required by PostgreSQL partitioning rules, not for semantic uniqueness.

**ORM impact:** SQLAlchemy ORM uses the PK tuple for identity. Code that currently does `db.get(TrackingEvent, event_id)` must change to `db.get(TrackingEvent, (event_id, event_ts))`. Audit of current code shows no such pattern — `TrackingEvent` is only ever written via `flush_detection_frame` and queried via `select(TrackingEvent).where(...)`. No change to application code is needed beyond the model definition.

### 2.4 Foreign Key Constraints

PostgreSQL 12+ supports FK references **from** a partitioned table to a non-partitioned table. Our two FKs are:

| FK | Direction | Valid? |
|---|---|---|
| `camera_id → cameras.camera_id (NO ACTION)` | partitioned → non-partitioned | Yes (PG 12+) |
| `person_id → persons.person_id (SET NULL)` | partitioned → non-partitioned | Yes (PG 12+) |

`PersonClipEmbedding.global_track_id` is **not** an FK to `tracking_events` — it is an unlinked UUID column. Partitioning `tracking_events` has no cascading impact on `person_clip_embeddings`.

### 2.5 Migration Strategy

The migration is a table-reconstruction approach that is safe on an empty DB (dev/test) and should be run inside a maintenance window on a live deployment.

**Steps (single Alembic migration):**

1. Rename `tracking_events` → `tracking_events_old`
2. Create `tracking_events` as `PARTITION BY RANGE (event_ts)` with composite PK `(event_id, event_ts)`, same constraints and FK as before
3. Create `tracking_events_default` (DEFAULT partition)
4. Create current-month partition: `tracking_events_y{YYYY}m{MM}`
5. Copy data: `INSERT INTO tracking_events SELECT * FROM tracking_events_old`
6. Reset the sequence to `MAX(event_id) + 1`
7. Recreate indexes on the parent (they propagate to children)
8. `DROP TABLE tracking_events_old`

**Downgrade:** Reconstruct a non-partitioned `tracking_events` from all partitions, then drop the partitioned version.

### 2.6 `PartitionManager`

Module: `vms/db/partition_manager.py`

```python
def ensure_future_partitions(engine: Engine, months_ahead: int = 3) -> None:
    """Create monthly partitions for current month + months_ahead months if absent."""

def drop_partitions_before(engine: Engine, cutoff: datetime) -> None:
    """Drop partitions whose upper bound <= cutoff. Skips DEFAULT partition."""

def list_partitions(engine: Engine) -> list[str]:
    """Return partition table names from pg_inherits."""
```

Called at application startup from `vms/db/session.py`. Also used by the Phase 5 nightly retention cron.

`ensure_future_partitions` is idempotent — uses `CREATE TABLE IF NOT EXISTS`.

### 2.7 Interaction with the Storage Abstraction

The two changes are independent. They touch different code paths and can be implemented in either order. Storage abstraction is recommended first because:
- It unblocks GDPR purge hardening that is independent of partitioning.
- Partitioning tests require an empty `tracking_events` table, which is already the case in the test suite.

### 2.8 Three-Tier Scaling Roadmap

This spec implements **Tier 1** capabilities (single server, up to ~200 cameras):

| Tier | Scale | Storage | DB | Identity |
|---|---|---|---|---|
| **1 (this spec)** | 1–200 cameras | Local or MinIO | PG 16 + monthly partitions | FAISS flat L2 |
| 2 (future) | 200–1000 cameras | Shared MinIO cluster | PG 16 + read replicas | FAISS IVF |
| 3 (future) | 1000+ cameras | S3-compatible + CDN | TimescaleDB or ClickHouse | pgvector HNSW |

No Tier 2/3 work is in scope for this plan. The `worker_group` column on `cameras` already anticipates Tier 2 multi-server ingest assignment.

---

## Invariants

- `thumbnail_path` and `snapshot_path` in DB are always **relative storage keys** after migration. Application code must not construct absolute paths from these columns.
- `PartitionManager` must be called at every application startup. Missing a month's partition is non-fatal (DEFAULT partition catches writes) but should alert.
- The DEFAULT partition must never be dropped — it is a safety net.
- Storage keys follow the `{prefix}/{YYYY}/{MM}/{DD}/{uuid4}.jpg` convention. Code must use the `generate_key()` helper from `vms/storage/backends.py`.
