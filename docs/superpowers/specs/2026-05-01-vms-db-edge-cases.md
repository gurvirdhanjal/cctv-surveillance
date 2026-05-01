# VMS v2 — Database Schema Edge Cases & Invariants

**Design Specification** · 2026-05-01
**Status:** Approved · Companion to `2026-05-01-vms-v2-hardened-design.md`
**Audience:** Engineers writing migrations, DB writers, FSM logic, and any code that mutates VMS state.

This document enumerates every production failure mode and edge case the v2 schema must handle, and the invariants every component must preserve. **Treat each row in the tables below as a test case — there should be a unit or integration test enforcing it.**

---

## Index

- §1 Concurrency & race conditions
- §2 Idempotency & retry safety
- §3 Cascade rules — what happens on delete / disable / archive
- §4 Partitioning, retention, and archival
- §5 Foreign key & referential integrity
- §6 Time, clock skew, timezones
- §7 Soft-delete & GDPR-style purge
- §8 Bulk write storms (alert storm, ingestion burst)
- §9 Backup, restore, and disaster recovery
- §10 Read replicas & consistency model
- §11 Schema migration safety
- §12 Index strategy, fragmentation, and online rebuild
- §13 Encryption at rest & sensitive data
- §14 Audit log invariants & hash-chain integrity
- §15 FAISS / DB consistency
- §16 Cross-component invariants

---

## §1. Concurrency & race conditions

| ID | Scenario | Failure mode if unhandled | Mitigation |
|---|---|---|---|
| C1 | Two ingestion workers publish frames for the same camera in overlapping windows | Duplicate `(camera_id, local_track_id, event_ts)` violates `uq_tracking_idem` → entire batch INSERT fails | DB writer uses `MERGE` (MSSQL) / `INSERT ... ON CONFLICT DO NOTHING` (SQLite test) keyed on the unique constraint. Per-row failure does not abort the batch |
| C2 | Alert FSM evaluates the same `(global_track_id, alert_type)` from two different inference replicas | Two `alert_fired` rows for what should be one alert | Dedup at FSM level: Redis Hash `alert_fsm:{type}:{zone_id}` with key = `global_track_id`, atomic `SET NX` to claim the alert before INSERT. TTL = cooldown |
| C3 | `zone_presence` open and close arrive out of order (network reorder or worker restart) | `exited_at < entered_at` row → analytics yield negative dwell | Identity service serialises presence transitions per `(zone_id, global_track_id)` via Redis lock. DB writer rejects rows where `exited_at < entered_at` (CHECK constraint) |
| C4 | `acknowledge` and `resolve` API calls race on the same alert | Lost acknowledged_by / acknowledged_at | Use `UPDATE alerts SET state='acknowledged', acknowledged_at=:now, acknowledged_by=:uid WHERE alert_id=:id AND state='active'`. If 0 rows affected, return 409 to caller |
| C5 | Two operators create the same maintenance window simultaneously | Duplicate windows for same scope+time, double-suppression noise | UI debounce + server `INSERT ... WHERE NOT EXISTS (SELECT 1 FROM maintenance_windows WHERE scope_type=? AND scope_id=? AND ...)`. Soft duplicate detection — warn but allow |
| C6 | FAISS rebuild from `person_embeddings` while enrolment is mid-INSERT | Newly enrolled person missing from index until next rebuild | Identity service holds an advisory lock during rebuild; enrolment API publishes a `faiss_dirty:add` Redis Stream event that triggers incremental add after rebuild completes |
| C7 | DB writer flushes tracking events while migration is running on `tracking_events` | Writer hangs or fails mid-batch | Migration runbook: pause DB writer (set Redis flag `db_writer_paused=1`) → wait for queue drain → run migration → unpause |
| C8 | Heartbeat expiry detection races with worker XAUTOCLAIM | Phantom "worker dead" admin alert when worker is just slow | Heartbeat check requires 2 consecutive misses 15s apart before alerting (TTL=15s, check every 10s, alert after >30s missing) |

### CHECK constraint additions

Add to `vms/db/models.py` and `alembic/versions/0001_initial_schema.py`:

```sql
ALTER TABLE zone_presence ADD CONSTRAINT chk_presence_temporal
    CHECK (exited_at IS NULL OR exited_at >= entered_at);

ALTER TABLE alerts ADD CONSTRAINT chk_alert_resolution_order
    CHECK (
        (acknowledged_at IS NULL OR acknowledged_at >= triggered_at)
        AND (resolved_at IS NULL OR resolved_at >= triggered_at)
        AND (resolved_at IS NULL OR acknowledged_at IS NULL OR resolved_at >= acknowledged_at)
    );

ALTER TABLE tracking_events ADD CONSTRAINT chk_bbox_valid
    CHECK (bbox_x2 > bbox_x1 AND bbox_y2 > bbox_y1);

ALTER TABLE maintenance_windows ADD CONSTRAINT chk_mw_window_positive
    CHECK (
        (schedule_type <> 'ONE_TIME' OR ends_at > starts_at)
        AND (schedule_type <> 'RECURRING' OR duration_minutes > 0)
    );

ALTER TABLE person_embeddings ADD CONSTRAINT chk_embedding_quality
    CHECK (quality_score >= 0.0 AND quality_score <= 1.0);
```

---

## §2. Idempotency & retry safety

Every writer in the system can be replayed (Redis XAUTOCLAIM after crash, network retry, manual replay from spillover JSON). The DB must accept the same logical event twice without producing duplicate state.

| Table | Idempotency key | Strategy |
|---|---|---|
| `tracking_events` | `(camera_id, local_track_id, event_ts)` | UNIQUE constraint `uq_tracking_idem`; writer uses MERGE |
| `alerts` | Application-level dedup key: `(alert_type, zone_id, dedup_window)` | FSM owns dedup; DB has no UNIQUE here (severity may upgrade an existing alert) |
| `alert_dispatches` | `(alert_id, channel, target, attempt_n)` | Implicit — `attempt_n` increments per retry; no UNIQUE because retries ARE distinct rows |
| `zone_presence` | `(zone_id, global_track_id, entered_at)` | UNIQUE (add this in v2.1 once we observe dedup pressure; v1 relies on identity-service serialisation) |
| `reid_matches` | None (audit trail; duplicates are acceptable noise) | None |
| `audit_log` | `audit_id` is the natural key; never re-write a row | Hash chain protects against silent duplicates being inserted later |
| `person_clip_embeddings` | `(global_track_id, event_ts)` — clip per tracklet at a moment | UNIQUE on this pair (add to migration) |

**Migration update needed:**

```sql
ALTER TABLE person_clip_embeddings ADD CONSTRAINT uq_clip_track_ts
    UNIQUE (global_track_id, event_ts);
```

---

## §3. Cascade rules — what happens on delete / disable / archive

The schema follows **soft-delete by default**. Hard deletes are explicit, audited, and forbidden via REST API for production tables.

| Action | What happens | Cascade |
|---|---|---|
| `Person.is_active = false` (employee leaves) | FAISS rebuild excludes person; live tracklets keep their `person_id` for audit | No cascade — historical data preserved |
| `Person` GDPR purge (`DELETE` API) | `is_active=false`, `purged_at=now`, embeddings blanked, thumbnails scrubbed from disk | `tracking_events.person_id` → kept for analytics integrity (un-FK'd in practice; nullable). `reid_matches.person_id` → set to a special "PURGED" sentinel person row, OR delete row depending on jurisdiction |
| `Camera.is_active = false` | Worker stops streaming; existing tracking_events keep `camera_id` | No cascade — historical events preserve camera link |
| `Camera` hard-delete | **FORBIDDEN via API.** Only allowed via Alembic data migration after archival of dependent rows | Manual: archive then DELETE — cascade to `cameras`-FK rows is restricted |
| `Zone.is_restricted` change | Future events use new value; historical events keep their zone_id | No cascade |
| `Zone` polygon edit | Future events evaluated against new polygon; historical events stay tagged with old `zone_id` (zone identity > zone shape) | No cascade |
| `Zone` hard-delete | **FORBIDDEN via API.** Same as cameras | Manual archival required |
| `User` deactivate (`is_active=false`) | JWT tokens still valid until expiry; user can't log in for new tokens | Tokens issued before deactivation continue to work — accept that <8h gap |
| `User` hard-delete | `acknowledged_by`, `created_by` (maintenance), `actor_user_id` (audit) become NULL | FK ON DELETE SET NULL on these; required to preserve audit trail |
| `MaintenanceWindow.is_active=false` | Stops applying immediately (calendar refresh ≤30s); historical alerts keep `suppressed_by_window_id` link | No cascade — alert linkage is historical fact |
| `AnomalyDetector.is_enabled=false` | InferenceEngine stops calling the detector on next config reload (≤60s); existing alerts unchanged | No cascade |

### FK declarations (consolidated)

```sql
-- audit + creator references that must survive user deletion
ALTER TABLE alerts            ADD CONSTRAINT fk_alerts_ack_user FOREIGN KEY (acknowledged_by)
    REFERENCES users(user_id) ON DELETE SET NULL;
ALTER TABLE maintenance_windows ADD CONSTRAINT fk_mw_creator FOREIGN KEY (created_by)
    REFERENCES users(user_id) ON DELETE NO ACTION;  -- must NOT delete user with windows
ALTER TABLE audit_log         ADD CONSTRAINT fk_audit_actor FOREIGN KEY (actor_user_id)
    REFERENCES users(user_id) ON DELETE SET NULL;

-- camera/zone references — restrict deletes
ALTER TABLE tracking_events   ADD CONSTRAINT fk_te_camera FOREIGN KEY (camera_id)
    REFERENCES cameras(camera_id) ON DELETE NO ACTION;
ALTER TABLE alerts            ADD CONSTRAINT fk_alerts_camera FOREIGN KEY (camera_id)
    REFERENCES cameras(camera_id) ON DELETE NO ACTION;
ALTER TABLE zone_presence     ADD CONSTRAINT fk_zp_zone FOREIGN KEY (zone_id)
    REFERENCES zones(zone_id) ON DELETE NO ACTION;
```

`ON DELETE CASCADE` is used **only** for tightly owned children: `person_embeddings → persons` and `user_*_permissions → users`.

---

## §4. Partitioning, retention, archival

`tracking_events` is the only high-write table in v1 (~14M rows/day at 52 cams). It is partitioned monthly via `pf_monthly`. Archival policy:

| Partition age | State | Action |
|---|---|---|
| Current month | Hot | Inserts + reads |
| 1–3 months old | Warm | Read-only; queries hit normal indexes |
| 4–12 months old | Cold | Move to a separate filegroup on slower disk; index rebuild to compressed format (PAGE compression) |
| > 12 months | Archive | Switch out partition → bulk-export to Parquet on object storage → drop partition |

### Partition rollover edge cases

- **Cron job creates next month's partition on the 25th of the current month** — gives 5 days of buffer. If the job fails, monitoring fires admin alert.
- **What if cron misses?** DB writer's MERGE will fail with "partition function range exceeded". Writer enters degraded mode (spillover JSON), emits CRITICAL alert. Manual fix: create the missing partition, pause writer, replay spillover, unpause.
- **Partition switch must NOT block live writes** — use `ALTER PARTITION SCHEME ... NEXT USED [filegroup]` while writes continue.
- **Empty future partitions** — pre-create partitions for next 12 months at install time (the migration creates 12 monthly anchors for 2026; a separate script extends yearly).

### Retention by table

| Table | Default retention | Override via |
|---|---|---|
| `tracking_events` | 12 months | Customer config |
| `alerts` | 7 years | Compliance requirements (audit) — never auto-delete in v1 |
| `audit_log` | 7 years (forever for compliance) | Same |
| `reid_matches` | 90 days | Customer config |
| `zone_presence` | 12 months | Customer config |
| `person_clip_embeddings` | 30 days (forensic search window) | §F.2 spec |
| `person_embeddings` | While person active; 30 days after `purged_at` for legal hold | GDPR config |
| `tracking_events` snapshot files (disk) | 90 days | Disk space config |

### Archive job runbook

`scripts/archive_old_tracking_events.py` runs nightly:

1. Identify partitions older than 12 months.
2. For each: `SWITCH OUT` to a staging table → `COPY` to Parquet on object storage (`s3://vms-archive/tracking_events/yyyy-mm/`) with checksum → verify → `DROP TABLE` staging → drop partition.
3. Records each step in `audit_log` with `event_type='ARCHIVE_PARTITION'`.
4. On any failure mid-pipeline, pauses and emits admin alert; never deletes raw data unless archive copy is verified.

---

## §5. Foreign key & referential integrity

| Concern | Risk | Mitigation |
|---|---|---|
| Orphaned `tracking_events` after camera hard-delete | History broken | FK with `ON DELETE NO ACTION` — DB rejects camera delete with dependent events. Operator must archive first |
| Orphaned `person_embeddings` after person purge | Embedding still in FAISS | Purge job deletes embeddings BEFORE rebuilding FAISS; FAISS rebuild is the source-of-truth refresh |
| `tracking_events.zone_id` is not FK'd | Drift if zone is renamed/deleted | Intentional — zones can be reshaped, but `zone_id` integer is stable. Validation: nightly job emits warning for `zone_id` values not present in `zones` |
| Cross-DB consistency between embeddings (DB) and FAISS index (memory) | Drift across restarts | FAISS always rebuilt from DB at startup; mid-flight changes go through `faiss_dirty` Redis Stream so the in-memory index stays consistent. See §15 |
| `alerts.suppressed_by_window_id` references a deleted window | Soft-delete keeps row | Maintenance windows are never hard-deleted. `is_active=false` only. FK is to `window_id` which is permanent |

---

## §6. Time, clock skew, timezones

**Storage convention:** all `DATETIME2` columns are **UTC**. The application converts to local time at the presentation layer. Database server timezone is irrelevant — `SYSUTCDATETIME()` is the canonical default.

| Edge case | Handling |
|---|---|
| Camera's NTP server is wrong | `event_ts` reflects camera's wall clock. Identity service compares `event_ts` to `ingest_ts` (worker clock). Skew >30s → drop event + admin alert |
| DST transition (spring forward / fall back) | UTC storage — no impact. Frontend renders in customer's local TZ via `date-fns-tz` with a configurable site timezone |
| Leap second | ignored — Windows / pyodbc / MSSQL handle as a 60→59 collapse. No correctness impact at the second-precision we use |
| Clock goes backwards on a worker (NTP step) | Writer detects: if `event_ts < last_seen_event_ts - 60s`, log warning + still insert (event_ts is camera time, not worker time). Idempotency constraint catches duplicates |
| "Now" in different processes | Use `func.current_timestamp()` (DB-side, MSSQL `SYSUTCDATETIME()`) for `created_at`; use Python `datetime.utcnow()` only when audit chain hash needs determinism (see §14) |
| `event_ts` granularity | `DATETIME2(3)` — millisecond. Sub-millisecond races handled by application-level monotonic `seq_id` (per-worker u64) |

### Required: timezone documentation in the API

Every API response containing a timestamp also returns the field as ISO-8601 with `Z` suffix (UTC). Clients render local time; server never converts.

---

## §7. Soft-delete & GDPR-style purge

Two distinct flows:

### A. Soft delete (employee leaves; data retained)

```python
person.is_active = False
session.commit()
write_audit_event(s, event_type="PERSON_DEACTIVATED", target_id=str(person.person_id))
faiss_dirty_stream.publish({"action": "remove", "person_id": person.person_id})
```

Effects:
- Person no longer matched against incoming embeddings (FAISS rebuild excludes inactive)
- Historical `tracking_events.person_id` retained
- API hides from search by default; admin filter shows inactive

### B. GDPR purge (subject access right / right to erasure)

```python
# vms/services/person_purge.py
def purge_person(session: Session, person_id: int, requester_id: int, reason: str) -> None:
    person = session.get(Person, person_id)
    if person is None:
        raise NotFound

    # 1. Mark inactive + record purge timestamp
    person.is_active = False
    person.purged_at = datetime.utcnow()
    person.thumbnail_path = None  # blank pointer

    # 2. Blank embeddings (zero out the bytes; keep rows for index integrity)
    for emb in person.embeddings:
        emb.embedding = b"\x00" * len(emb.embedding)
        emb.quality_score = 0.0

    # 3. Scrub thumbnails from disk
    purge_thumbnail_files(person_id)

    # 4. Clip embeddings — these CAN be deleted because they're per-event, not per-identity
    session.query(PersonClipEmbedding).filter_by(...).delete()
    # Note: can't filter by person_id here because clip embeddings track global_track_id,
    # not person_id directly. Use a join through tracking_events:
    # DELETE FROM person_clip_embeddings WHERE global_track_id IN
    #   (SELECT DISTINCT global_track_id FROM tracking_events WHERE person_id = :pid)

    # 5. tracking_events.person_id retained (analytics integrity)
    #    But we record purge for legal hold

    write_audit_event(session, event_type="PERSON_PURGED",
                      actor_user_id=requester_id,
                      target_type="person", target_id=str(person_id),
                      payload={"reason": reason, "embeddings_blanked": len(person.embeddings)})

    # 6. Trigger FAISS rebuild
    faiss_dirty_stream.publish({"action": "remove", "person_id": person_id})

    session.commit()
```

### Edge cases for purge

- **Concurrent enrolment for the same person mid-purge** — purge holds a row-level lock on `persons` via `SELECT ... FOR UPDATE`; enrolment retries
- **Purge fails mid-step (e.g., disk error scrubbing thumbnails)** — entire transaction rolls back; partial state not left in DB. Disk scrubbing happens in a separate transaction guarded by `purged_at IS NOT NULL` precondition
- **Court order to RESTORE a purged person** — by design, blanked embeddings cannot be reconstructed. Document this for legal counsel; if restore needed, customer must re-enrol

---

## §8. Bulk write storms

| Storm | Cause | Without mitigation | Mitigation |
|---|---|---|---|
| Tracking event burst (~50k rows in 2s) | All cameras boot simultaneously after power outage | DB writer overwhelmed → spillover | Batched writes (100 rows / 500ms); spillover JSON file is bounded; rate-limited drain on recovery |
| Alert storm (50 alerts in 1s) | Crowd disperses across all zones | Frontend WS flood + dispatcher saturates Slack rate limits | Server dedup 60s window per `(type+zone)`; dispatcher queues with per-channel rate limits (Slack: 1/s, Telegram: 30/s, webhook: 100/s) |
| Audit log spike (every alert + every operator click) | Big incident, lots of guard activity | Hash-chain serialisation becomes a write bottleneck | Audit writes go through a single dedicated writer goroutine/coroutine that serialises hash computation. Throughput ceiling ~1k rows/s — sufficient for 52-cam plant. If exceeded, batch-mode hash chain (group N events under one chain link) |
| FAISS-dirty event flood | Mass enrolment | FAISS rebuild thrashes | Coalesce: enrolment events buffered for 5s, then single rebuild |
| Snapshot disk I/O spike | All cameras snapshot at the same instant for periodic API refresh | Disk saturation, latency spike | Stagger snapshot timestamps per-camera by `cam_id mod refresh_interval_ms` |

---

## §9. Backup, restore, disaster recovery

### RPO / RTO targets

| Tier | RPO | RTO | Backup mechanism |
|---|---|---|---|
| Production single-site | 15 min | 1 hour | MSSQL full backup nightly + tlog backup every 15 min to local + offsite |
| Critical incident period | 5 min | 30 min | (manual) tlog backups every 5 min during high-risk operational windows |

### What's NOT in the backup

- FAISS index (rebuilt from `person_embeddings` on restart; never persisted to disk)
- Redis state (regenerable from MSSQL + camera streams; degraded mode handles outage)
- Snapshot files (separate object-storage backup; PIT recovery via storage versioning)
- Model files (`models/v{N}/`; restored via `vms-models download` + manifest checksum verify)

### Restore drill — must run quarterly

```
1. Spin up a parallel MSSQL instance.
2. Restore latest full backup + all tlog files up to target PIT.
3. Run `alembic current` — confirm head matches production.
4. Run `vms-models download` against the customer's mirror.
5. Start identity service → confirm FAISS rebuild from restored persons table.
6. Run `GET /api/audit/verify` end-to-end → expect no broken hash links.
7. Run `vms-doctor` self-test (ships in Phase 5) → expect green.
```

Each drill recorded in `audit_log` with `event_type='DR_DRILL'`.

### Edge cases

- **Backup taken mid-batch-flush** — tlog captures a transactionally consistent point; safe.
- **Restore to an earlier point than current `audit_log` head** — hash chain integrity remains, but operators see "events from the future" in audit if they replay logs. Document: restore is a discrete action; the `audit_log` records the restore event with a special hash-link explanation.
- **Sysprep / SQL Server reinstall loses encryption key** — see §13.

---

## §10. Read replicas & consistency model

v1 is single-node MSSQL. The schema is designed so that adding read replicas in v2.1 is non-breaking:

- All API reads can use `READ COMMITTED SNAPSHOT ISOLATION` (RCSI) — turn this on at DB level: `ALTER DATABASE vms_dev SET READ_COMMITTED_SNAPSHOT ON;`. Avoids reader/writer blocking entirely.
- Every endpoint that requires read-after-write consistency (e.g., enrolment) routes to primary explicitly via a session flag.
- Eventually-consistent reads (timeline, analytics, search) can use replica.

Edge cases when replicas are added:

- **Stale read on freshly-enrolled person** — enrolment returns synchronously; FAISS rebuild waits for primary commit before publishing `faiss_dirty`. Replica catch-up doesn't affect FAISS path.
- **Audit verify on replica** — fine; verify is read-only and replica eventually catches up.
- **Migration with replicas** — apply on primary; replica catches up. Avoid migrations during peak ops.

---

## §11. Schema migration safety

| Migration type | Safe to run on live system? | Approach |
|---|---|---|
| `ADD COLUMN` (nullable, no default) | Yes | Routine; runs in seconds even on huge tables |
| `ADD COLUMN NOT NULL DEFAULT` | No (without care) | Use two-step: ADD nullable → backfill in batches → ALTER to NOT NULL |
| `DROP COLUMN` | Yes (if no app reference) | Routine. Confirm via `mypy + grep` first |
| `ADD INDEX` (online) | Yes (MSSQL Enterprise) / Maintenance window (Standard) | Use `CREATE INDEX ... WITH (ONLINE=ON)` on Enterprise; offline elsewhere |
| `ALTER COLUMN` (type change) | Maintenance window only | Especially risky on `tracking_events` due to size |
| Foreign key add / drop | Maintenance window | Brief table lock |
| New CHECK constraint on populated table | Maintenance window | DB scans full table; use `WITH NOCHECK` then validate offline |
| New table | Yes | Routine |
| Partition function alter | Maintenance window | Concurrency with DB writer paused |

### Pre-flight checklist for any migration

1. `alembic current` — confirm at expected head
2. Migration includes `downgrade()` that's tested
3. Pause DB writer if migration touches `tracking_events`
4. Take fresh tlog backup before applying
5. Run on staging clone first
6. Apply to production
7. `alembic current` — confirm new head
8. Resume writers
9. Record in `audit_log` with `event_type='SCHEMA_MIGRATION'`

### Rollback drill — must run quarterly

For each shipped migration, verify `alembic downgrade -1` succeeds on a staging clone of production.

---

## §12. Index strategy, fragmentation, online rebuild

### Initial index plan (already in migration 0001)

```sql
-- foreign keys auto-indexed below
ix_persons_employee_id          ON persons (employee_id)
ix_person_embeddings_person_id  ON person_embeddings (person_id)
ix_tracking_events_global_track_id, _person_id, _camera_id, _event_ts
ix_reid_global_track, ix_reid_person
ix_zone_presence_zone_id, _global_track
ix_alerts_alert_type, _triggered_at
ix_dispatches_alert
ix_clip_global_track, ix_clip_event_ts
ix_audit_event_ts, ix_audit_target
```

### Filtered indexes — added in Phase 5 (MSSQL only, not in initial migration)

These match query patterns we expect to see when the API is built:

```sql
-- "who is currently in this zone?"
CREATE INDEX ix_zp_active ON zone_presence (zone_id, entered_at DESC)
    WHERE exited_at IS NULL;

-- "active alerts" (the only query the alert sidebar runs in real time)
CREATE INDEX ix_alerts_active ON alerts (state, triggered_at DESC)
    WHERE state = 'active';

-- "currently-active maintenance windows"
CREATE INDEX ix_mw_active_scope ON maintenance_windows (scope_type, scope_id)
    WHERE is_active = 1;
```

These filtered indexes are MSSQL-specific (SQLite supports them too but SQLAlchemy autogen doesn't always emit). Add via raw SQL in a Phase 5 migration when query patterns are observable.

### Fragmentation maintenance

Schedule a SQL Agent job nightly:

```sql
-- on each user table, rebuild indexes with fragmentation > 30%, reorganise > 10%
-- Use Ola Hallengren's IndexOptimize stored procedure (industry standard)
EXEC dbo.IndexOptimize @Databases = 'vms_dev',
    @FragmentationLow = NULL,
    @FragmentationMedium = 'INDEX_REORGANIZE',
    @FragmentationHigh = 'INDEX_REBUILD_ONLINE',
    @FragmentationLevel1 = 5,
    @FragmentationLevel2 = 30,
    @UpdateStatistics = 'ALL';
```

### Edge cases

- **Index rebuild on `tracking_events`** — billions of rows; ONLINE rebuild required to avoid downtime. Standard Edition cannot do this — add to deployment requirements (Enterprise needed at scale > 200M rows).
- **Stats out of date after migration** — last step of any migration that adds rows: `UPDATE STATISTICS <table>;`

---

## §13. Encryption at rest & sensitive data

### Sensitive columns

| Table.column | Why | At-rest encryption |
|---|---|---|
| `person_embeddings.embedding` | Biometric data; reversible to face under research attacks | Fernet-encrypted at application layer; key in env / DPAPI / vault. Decrypt only on FAISS rebuild |
| `persons.thumbnail_path` (the file at this path) | Face image | Disk-level encryption: BitLocker on Windows, LUKS on Linux. **Path itself is not sensitive** |
| `users.password_hash` | Auth credential | bcrypt (already a hash; not a secret per se but never log). Use cost factor ≥ 12 |
| `cameras.rtsp_url` | Contains RTSP credentials | Encrypted at app layer with the same key as embeddings. Decrypted in worker process, never returned via API except to admin |
| `alert_routing.target` | Webhook URLs may contain tokens | Same — encrypt at app layer for any value that looks like a URL with credentials or a Slack channel |
| `audit_log.payload` | May contain PII | Reviewed per event_type; PII fields hashed in payload, raw value held only in the source table |

### Encryption helper module

`vms/security/at_rest.py` (Phase 5):

```python
class AtRestCipher:
    def __init__(self, key_b64: str) -> None:
        self._fernet = Fernet(key_b64.encode())

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._fernet.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self._fernet.decrypt(ciphertext)
```

### Key management

- **Single key per deployment**, stored in env var `VMS_AT_REST_KEY` on Linux or DPAPI-protected on Windows.
- **Rotation**: support two keys in parallel (`VMS_AT_REST_KEY_CURRENT`, `VMS_AT_REST_KEY_PREVIOUS`); decrypt tries both, encrypt uses current. Migration job rolls all rows forward, then `PREVIOUS` is removed.
- **Lost key** = data loss for affected columns. Document this prominently in operations runbook.

### Edge cases

- **Backup includes encrypted blobs but not key** — restore on a new machine without the key = useless data. Operations runbook: key escrow with the customer's IT / vault.
- **Embedding decrypt during FAISS rebuild is the hot path** — use threadpool to parallelise; benchmark — for 6 enrolled employees and 30 embeddings per person, total decrypt time should be <1s. With 1000 employees, ~30s — acceptable for startup. Beyond that, cache decrypted index on shutdown (encrypted file) and refresh incrementally.

---

## §14. Audit log invariants & hash-chain integrity

### Invariants (must hold at all times)

1. `audit_log.audit_id` is gap-free monotonic from 1.
2. For every row N>1: `row_N.prev_hash == row_{N-1}.row_hash`.
3. `row_1.prev_hash == GENESIS_HASH ('0' * 64)`.
4. `row_hash` is reproducible from the canonical concatenation of fields (see `vms/db/audit.py:compute_row_hash`).
5. No row is ever updated after insert.

### Verification endpoint

`GET /api/audit/verify?from=&to=` walks the chain in chunks of 1000 rows, returning:

```json
{
  "rows_checked": 1234567,
  "broken_chain_at": null,
  "duration_ms": 4321
}
```

If any row's `prev_hash` doesn't match the previous row's `row_hash`, returns the offending `audit_id` and stops.

### Edge cases

- **Power loss between INSERT and chain advance in another writer** — hash chain serialised through a single audit-writer process; only one outstanding INSERT at a time. Power loss at most loses the in-flight event.
- **Two processes write audit rows concurrently** — must NOT happen. Code path: every audit write goes through `vms.db.audit.write_audit_event` which acquires a `SELECT ... FOR UPDATE` on the latest `audit_log` row inside the same transaction. MSSQL: `WITH (UPDLOCK, HOLDLOCK)` on the SELECT.
- **Schema migration that adds a column to `audit_log`** — hash computation is over a fixed set of fields (defined in `compute_row_hash`); adding a column doesn't break existing hashes. New column not part of hash unless we explicitly version-bump the hash function (and even then, document a chain-link breakpoint).
- **Restore from backup mid-day** — the restore creates a "fork" in the chain. Add an `event_type='RESTORE_FORK'` row that records the restore operation, with `prev_hash` = the latest pre-restore hash. Verify endpoint flags this as expected, not broken.
- **Hash function future change** — version field (`row_hash_version`) added in v2.x for forward compat. Default `v1`.

---

## §15. FAISS / DB consistency

FAISS indices (face embeddings + CLIP embeddings) are derived caches. The DB is the source of truth.

### Lifecycle

1. **Startup:** identity service reads all active embeddings → builds FAISS in memory. Time budget: see §13.
2. **Enrolment:** API writes to DB → publishes `faiss_dirty` Redis Stream event → identity service `add()` to in-memory index.
3. **Purge:** API blanks embeddings → publishes `faiss_dirty` action=remove → identity service `remove_ids()` (FAISS supports it for IDMap indices).
4. **Crash recovery:** identity service rebuilds from scratch on restart. Pending `faiss_dirty` events replayed via Redis Streams consumer group.

### Drift detection

A nightly job:
1. Counts active embeddings in DB.
2. Counts vectors in FAISS index (via the identity service `/internal/index-stats` endpoint — admin only).
3. Alerts if differ by > 5 (allows for a couple of in-flight enrolments).

### Edge cases

- **Identity service restarts mid-rebuild** — incomplete index. Service refuses to serve traffic until rebuild completes (Redis health key `identity_ready=0` until done).
- **Embedding removed from DB but `remove_ids` failed** — drift; nightly job catches it, triggers full rebuild.
- **CLIP index outgrows memory** (after ~6 months at 100 detections/min) — implement IVF-PQ index instead of flat IP. Budget: hold flat for first 30 days, IVF-PQ for older. Hybrid query merges both.

---

## §16. Cross-component invariants

Truth-table style: each row is a property the system must always satisfy.

| Invariant | Enforced by |
|---|---|
| Every `tracking_events` row has a corresponding `cameras` row | FK |
| If `tracking_events.person_id IS NOT NULL`, then `persons` row exists | FK |
| Every active `alerts` row with `acknowledged_by IS NOT NULL` has matching `users` row | FK SET NULL on user delete |
| `zone_presence.exited_at >= entered_at` always | CHECK constraint |
| `alerts` resolution timestamps are non-decreasing (triggered ≤ acknowledged ≤ resolved) | CHECK constraint |
| `audit_log` rows are immutable | App-layer convention; DB triggers REJECT updates / deletes (Phase 5) |
| `maintenance_windows` ONE_TIME implies starts/ends both set; RECURRING implies cron+duration set | CHECK constraint |
| `cameras.capability_tier IN ('FULL','MID','LOW')` | CHECK constraint |
| `alerts.state IN ('active','acknowledged','resolved','suppressed')` | CHECK constraint |
| `alert_routing.channel IN ('EMAIL','SLACK','TELEGRAM','WEBHOOK','WEBSOCKET')` | CHECK constraint |
| `tracking_events.bbox_x2 > bbox_x1 AND bbox_y2 > bbox_y1` | CHECK constraint |
| `person_embeddings.quality_score ∈ [0, 1]` | CHECK constraint |
| `(camera_id, local_track_id, event_ts)` unique in `tracking_events` | UNIQUE constraint |
| `(global_track_id, event_ts)` unique in `person_clip_embeddings` | UNIQUE constraint |
| FAISS active-vector count == DB active-embedding count (modulo 5) | Nightly drift check |

### Test coverage rule

For each row in this table, there is a corresponding test (in `tests/test_db_invariants.py` — Phase 1B work, **not Phase 1A**) that asserts the invariant. Adding a new invariant means adding a new test in the same file.

---

## §17. DDL update summary

This document calls for the following additions to the initial migration (`alembic/versions/0001_initial_schema.py`). Apply via amendment to the migration file before first run, or via a small follow-up `0002_invariants.py`:

```sql
-- §1 CHECK constraints
ALTER TABLE zone_presence ADD CONSTRAINT chk_presence_temporal
    CHECK (exited_at IS NULL OR exited_at >= entered_at);

ALTER TABLE alerts ADD CONSTRAINT chk_alert_resolution_order
    CHECK (
        (acknowledged_at IS NULL OR acknowledged_at >= triggered_at)
        AND (resolved_at IS NULL OR resolved_at >= triggered_at)
        AND (resolved_at IS NULL OR acknowledged_at IS NULL OR resolved_at >= acknowledged_at)
    );

ALTER TABLE tracking_events ADD CONSTRAINT chk_bbox_valid
    CHECK (bbox_x2 > bbox_x1 AND bbox_y2 > bbox_y1);

ALTER TABLE maintenance_windows ADD CONSTRAINT chk_mw_window_positive
    CHECK (
        (schedule_type <> 'ONE_TIME' OR ends_at > starts_at)
        AND (schedule_type <> 'RECURRING' OR duration_minutes > 0)
    );

ALTER TABLE person_embeddings ADD CONSTRAINT chk_embedding_quality
    CHECK (quality_score >= 0.0 AND quality_score <= 1.0);

-- §2 idempotency
ALTER TABLE person_clip_embeddings ADD CONSTRAINT uq_clip_track_ts
    UNIQUE (global_track_id, event_ts);

-- §3 cascade declarations
ALTER TABLE alerts ADD CONSTRAINT fk_alerts_ack_user
    FOREIGN KEY (acknowledged_by) REFERENCES users(user_id) ON DELETE SET NULL;
ALTER TABLE audit_log ADD CONSTRAINT fk_audit_actor
    FOREIGN KEY (actor_user_id) REFERENCES users(user_id) ON DELETE SET NULL;
-- maintenance_windows.created_by intentionally NO ACTION (must not delete user with windows)
```

The Phase 1A plan (`2026-05-01-vms-v2-phase1a-db-schema.md`) Task 13 is **updated** to include these constraints in `0001_initial_schema.py`. The plan's task body should be edited to merge these constraints into the relevant table definitions before the first `alembic upgrade head` runs — preserving the "ship the full v2 schema in migration 0001" principle.

---

**End of edge-cases spec.**
