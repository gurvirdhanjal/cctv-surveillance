# Phase 1A.2 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE** — 171 tests passing as of commit `210b283` (2026-05-28)

**Goal:** Close two Phase 1A correctness gaps: (1) deprecated `datetime.utcnow` in ORM
column defaults, (2) missing `row_hash_version` column on `audit_log` that allows future
hash algorithm migration without chain-link confusion.

**Architecture:** ORM + Alembic migration only. No new modules. No API surface changes.

**Tech Stack:** SQLAlchemy 2.x mapped_column, Alembic, pytest.

**Spec refs:**
- `docs/superpowers/specs/2026-05-01-vms-db-edge-cases.md` §4 (audit log immutability)
- CLAUDE.md §5 (timezone convention), §6.4 (audit log rules)

---

## Task 1: Replace deprecated `datetime.utcnow` in ORM column defaults (T1)

- [x] 1.1 Add `_utcnow_naive()` helper in `vms/db/models.py`
- [x] 1.2 Replace all 8 `default=datetime.utcnow` calls with `default=_utcnow_naive`
- [x] 1.3 Verify `ruff check` passes (no B008 bare call warnings)
- [x] 1.4 Commit: `fix: replace deprecated datetime.utcnow with timezone-aware UTC in models and persons endpoint`

## Task 2: Add `row_hash_version` column to `audit_log` (T2)

- [x] 2.1 Add `row_hash_version: Mapped[int]` column to `AuditLog` ORM class in `vms/db/models.py`
- [x] 2.2 Update `write_audit_event()` in `vms/db/audit.py` to populate `row_hash_version=ROW_HASH_VERSION`
- [x] 2.3 Write Alembic migration `alembic/versions/a1b2c3d4e5f6_add_row_hash_version_to_audit_log.py`
- [x] 2.4 Add test `test_row_hash_version_is_persisted` in `tests/test_db_audit.py`
- [x] 2.5 Verify migration round-trip (upgrade/downgrade) on test DB
- [x] 2.6 Commit: `feat: add row_hash_version column to audit_log for future algorithm migration`
