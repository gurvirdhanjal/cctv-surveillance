# VMS Foundation Hardening & Docs Cleanup Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [x]`) syntax for tracking.

**Status: COMPLETE** — 176 tests passing as of commit `3bd6669` (2026-05-28)

**Goal:** Close cascading-failure risks across the entire VMS docs and code foundation
before Phase 2b implementation begins. Remove noise. Establish production-readiness
gates. Fix naming inconsistencies. Add the one integration test that proves the pipe
works end-to-end.

**Architecture:** This is a foundation-cleanup plan. No new business logic. New specs,
new runbooks, file moves, one config field, one integration test, CLAUDE.md updates.

**Spec refs:**
- All 4 current specs in `docs/superpowers/specs/`
- CLAUDE.md §2 (legacy files), §3 (phase status), §12 (RTSP threshold)
- Decision log from `/plan-eng-review` 2026-05-27

---

## Decision log

| D# | Decision | Choice |
|---|---|---|
| D1 | Production readiness exit criteria | A: write spec now |
| D2 | System-health alerting | A: dedicated channel + ops routing (Phase 3 scope addition) |
| D3 | Data retention / pruning | A: configurable per-table retention (Phase 5 scope addition) |
| D4 | Install/upgrade/backup/DR docs | A: four runbooks under `docs/runbooks/` |
| D5 | Customer onboarding flow | A: write `docs/runbooks/customer-onboarding.md` now |
| D6 | Noise removal | A: move legacy .py to `legacy/`, delete superseded plan |
| D7 | Phase 1A/1B status taxonomy | B: rename to subphase (phase1a-1, phase1a-2, phase1b-1, phase1b-2) |
| D8 | RTSP failure threshold | A: config-driven `rtsp_failure_threshold` (default 5) |
| D9 | End-to-end integration test | A: full-pipeline E2E with synthetic frame source |
| D10 | Soak / load test timing | B: defer to Phase 5 Camera Rollout |

---

## Cascading failure map (what this plan closes)

```
                ┌─────────────────────────────────────────────┐
                │  Production deployment hits paying customer  │
                └────────────────────┬─────────────────────────┘
                                     │
        ┌────────────────────────────┼──────────────────────────────┐
        │                            │                              │
        ▼                            ▼                              ▼
   No retention            No install/backup/             No system health
   policy → disk           DR runbook →                   alerts → camera
   fills month 3           panic on day 1                 drops silent
        │                            │                              │
   Fixed by D3                  Fixed by D4                    Fixed by D2
   (Phase 5)                    (this plan)                    (Phase 3)

        ┌────────────────────────────┼──────────────────────────────┐
        │                            │                              │
        ▼                            ▼                              ▼
   Contract drift           Capacity claims              Foundation has
   between modules →        unvalidated → leak at        known bugs but
   prod surprise            hour 30 of soak              status says DONE
        │                            │                              │
   Fixed by D9                  Fixed by D10                   Fixed by D7
   (this plan)                  (Phase 5)                      (this plan)
```

---

## Task 1: Write Production Readiness Spec (D1)

**Background:** No doc enumerates what \"sellable v1\" means. Each phase ships in
isolation; gaps surface during paid deployment.

### Subtasks

- [x] 1.1 Create `docs/superpowers/specs/2026-05-27-vms-production-readiness.md`
- [x] 1.2 Required sections:
  - **Service level objectives** (uptime target, frame ingestion latency p50/p99,
    alert dispatch latency p99, FAISS staleness ceiling)
  - **Security audit gates** (OWASP top 10 pass, dependency CVE scan clean, JWT
    handling reviewed, secrets management documented, RTSP credential redaction
    verified)
  - **GDPR audit gates** (data inventory, retention policy from D3, purge
    procedure proven, audit log immutability proven, right-to-access export)
  - **Operational gates** (install runbook tested on fresh VM, backup proven on
    test data, DR procedure tested, 24h soak passed from D10)
  - **Documentation gates** (CLAUDE.md current, all phase plans status-accurate,
    onboarding runbook validated by external tester, EXPLAINER.md links current)
  - **Capacity claims** (concrete numbers per GPU SKU, validated by soak)
  - **Per-phase gate-closing matrix** (which phase delivers which gate)
- [x] 1.3 Each gate states: criterion, owner phase, evidence required, status
- [x] 1.4 Link from CLAUDE.md §1 as the v1-GA acceptance spec
- [x] 1.5 Commit: `docs: add production readiness spec defining v1 GA exit criteria`

---

## Task 2: Repo tidy — legacy/ directory + delete superseded plan (D6)

**Background:** Eight prototype .py files at repo root + a self-declared
superseded plan create onboarding confusion.

### Subtasks

- [x] 2.1 Create `legacy/` directory at repo root
- [x] 2.2 `git mv` each legacy file to `legacy/`:
  ```
  git mv main.py face_detection.py enrollment_emp.py face_utils.py
  git mv scrfd_face.py test.py test_db.py config.py legacy/
  ```
- [x] 2.3 Add `legacy/README.md`:
  ```markdown
  # Legacy prototype files

  Pre-Phase 1A prototype code, kept for reference only.
  **Do not import, edit, or run.**

  Production code lives in `vms/`. See CLAUDE.md §2.
  ```
- [x] 2.4 Add `legacy/` to ruff and mypy excludes in pyproject.toml
- [x] 2.5 `git rm docs/superpowers/plans/2026-04-23-phase1-foundation.md`
  (git history preserves it; `git show <commit>:<path>` recovers)
- [x] 2.6 Update CLAUDE.md §2: remove the legacy file list; replace with one
  sentence: \"Legacy prototype code is in `legacy/`. Do not import.\"
- [x] 2.7 Verify `ruff check vms/ tests/` still passes (no legacy imports broken)
- [x] 2.8 Commit: `chore: move legacy prototype files to legacy/ and delete superseded phase 1 plan`

---

## Task 3: Rename completed plans to subphase taxonomy (D7)

**Background:** Phase 1A/1B \"COMPLETE\" status is misleading when a hardening
plan documents 7 known bugs. Subphase taxonomy (1A.1, 1A.2, 1B.1, 1B.2) makes
the relationship explicit.

### Subtasks

- [x] 3.1 Rename plans:
  ```
  git mv docs/superpowers/plans/2026-05-01-vms-v2-phase1a-db-schema.md \
         docs/superpowers/plans/2026-05-01-vms-v2-phase1a-1-db-schema.md

  git mv docs/superpowers/plans/2026-05-09-vms-v2-phase1b-ingestion-inference-api.md \
         docs/superpowers/plans/2026-05-09-vms-v2-phase1b-1-ingestion-inference-api.md
  ```
- [x] 3.2 Split the hardening-fixes plan into two:
  - `2026-05-27-vms-v2-phase1a-2-hardening.md` — contains the audit-log row_hash_version
    fix (T2), datetime.utcnow column-default fix (T1, the 8 in models.py only)
  - `2026-05-27-vms-v2-phase1b-2-hardening.md` — contains SHM validation (T4),
    RTSP backoff + session_factory (T5), GDPR purge completeness (T3),
    persons.py:125 utcnow line, evict_stale wiring (T6), faiss_dirty consumer (T7)
  - Delete the combined `2026-05-27-vms-v2-phase1ab-hardening-fixes.md`
- [x] 3.3 Update CLAUDE.md §3 phase status section:
  ```markdown
  We are at **Phase 2b: Anomaly Framework** (plan reviewed; implementation NOT
  STARTED).

  **Foundation Hardening & Docs Cleanup** is **NOT STARTED** — plan:
  `docs/superpowers/plans/2026-05-27-vms-foundation-hardening-and-docs-cleanup.md`.
  This plan must land before Phase 2b implementation begins.

  **Phase 1B.2 Hardening** is **NOT STARTED** — plan:
  `docs/superpowers/plans/2026-05-27-vms-v2-phase1b-2-hardening.md`. Closes 5 known
  bugs from Phase 1B (SHM, RTSP, GDPR purge, evict_stale, faiss_dirty consumer).

  **Phase 1A.2 Hardening** is **NOT STARTED** — plan:
  `docs/superpowers/plans/2026-05-27-vms-v2-phase1a-2-hardening.md`. Closes
  audit-log forward-compat + datetime.utcnow column defaults.

  **Phase 2a Hardening (2a.2)** is **COMPLETE** — 159 tests passing as of commit `019e45e`.
  Plan: `docs/superpowers/plans/2026-05-14-vms-v2-phase2a-2-hardening.md`. (Was named
  phase2a-hardening; renamed for taxonomic consistency.)

  **Phase 2a Identity (2a.1)** is **COMPLETE** ...

  **Phase 1B.1** (initial Ingestion/Inference/API) is **COMPLETE** ...

  **Phase 1A.1** (initial DB Schema) is **COMPLETE** ...
  ```
- [x] 3.4 Optionally rename `2026-05-14-vms-v2-phase2a-hardening.md` →
  `2026-05-14-vms-v2-phase2a-2-hardening.md` and `2026-05-14-vms-v2-phase2a-identity-framework.md`
  → `2026-05-14-vms-v2-phase2a-1-identity-framework.md` for consistency.
- [x] 3.5 Update each renamed plan's `**Status:**` line to clarify subphase number
- [x] 3.6 Commit: `docs: rename plans to subphase taxonomy (1A.1, 1A.2, 1B.1, 1B.2, 2a.1, 2a.2)`

---

## Task 4: Four ops runbooks (D4)

**Background:** No install, upgrade, backup, or DR docs exist.

### Subtasks

- [x] 4.1 Create `docs/runbooks/` directory
- [x] 4.2 Write `docs/runbooks/install.md`:
  - Hardware prerequisites (GPU SKU, RAM, disk, network)
  - OS prerequisites (Ubuntu 22.04 + nvidia-container-toolkit, or Windows Server 2022)
  - Docker compose recipe for prod (PostgreSQL 16 + Redis 7 + nginx + vms-app)
  - Bare-metal install procedure (systemd units)
  - Post-install verification (`vms-cli doctor`)
  - Common install errors and fixes
- [x] 4.3 Write `docs/runbooks/upgrade.md`:
  - Pre-upgrade backup procedure
  - Alembic migration application order
  - Model manifest update procedure
  - Zero-downtime rollout (blue/green via nginx upstream swap)
  - Rollback procedure if upgrade fails
  - Post-upgrade smoke test
- [x] 4.4 Write `docs/runbooks/backup-restore.md`:
  - What to back up: PostgreSQL `pg_dump`, FAISS rebuild from DB (no backup needed),
    face thumbnails directory, model manifest lockfile, configuration secrets
  - Backup schedule recommendation (nightly DB dump, weekly full filesystem)
  - Restore procedure: stop services, restore DB, restart, FAISS auto-rebuilds
  - Restore validation: verify last 5 audit events chain-link, test one search query
- [x] 4.5 Write `docs/runbooks/disaster-recovery.md`:
  - RTO/RPO targets (recommend 4h RTO, 24h RPO for plant CCTV)
  - Server-down procedure: cold-spare hardware swap, restore from backup
  - GPU failure procedure: degraded mode (ingestion-only, no inference)
  - Network partition procedure: alert dispatch fallback to local SMTP relay
  - Full-site loss procedure: rebuild from offsite backup
- [x] 4.6 Index file: `docs/runbooks/README.md` listing all runbooks
- [x] 4.7 Each runbook: numbered steps, no prose-only sections, end with verification
- [x] 4.8 Commit: `docs: add install / upgrade / backup-restore / disaster-recovery runbooks`

---

## Task 5: Customer onboarding runbook (D5)

**Background:** Fragmented across multiple specs. Internal testers need one walkthrough.

### Subtasks

- [x] 5.1 Write `docs/runbooks/customer-onboarding.md`:
  - **Step 1 — Server install** (link to install.md)
  - **Step 2 — Create first admin user** (`vms-cli users create --admin`)
  - **Step 3 — Network camera discovery** (network scan, RTSP probe)
  - **Step 4 — Run CameraProfiler per camera** (yields FULL/MID/LOW tier;
    produces signed site-readiness PDF)
  - **Step 5 — Calibrate homography for each camera** (4-point pick on floor plan;
    reprojection error < 2px)
  - **Step 6 — Define zones** (polygon draw; assign maintenance windows;
    set adjacency for cross-camera tracking)
  - **Step 7 — Configure RBAC** (create operator users, assign camera + zone
    permissions)
  - **Step 8 — Enrol first persons** (`POST /api/persons` + at least 3 embeddings
    per person from different angles)
  - **Step 9 — Configure alert routing** (SMTP, Slack, Telegram, webhook;
    test dispatch)
  - **Step 10 — Run acceptance test** (walk an enrolled person + unknown person
    through Camera 1, verify alerts fire correctly)
- [x] 5.2 Each step lists: prerequisites, exact commands or API calls, expected
  output, troubleshooting
- [x] 5.3 Phase 4 frontend implements this as a wizard UI; this doc is the spec
- [x] 5.4 Commit: `docs: add customer onboarding runbook covering install-to-first-alert flow`

---

## Task 6: Config-driven RTSP failure threshold (D8)

**Background:** CLAUDE.md says 3 fails; hardening plan T5 hardcodes 5. Make it
config-driven.

### Subtasks

- [x] 6.1 Add to `vms/config.py` Settings class:
  ```python
  rtsp_failure_threshold: int = 5
  rtsp_backoff_delays_ms: tuple[int, ...] = (1000, 2000, 4000, 8000, 60000)
  ```
- [x] 6.2 Update Phase 1B.2 hardening plan T5 to read from `get_settings()`:
  ```python
  settings = get_settings()
  _BACKOFF_DELAYS = [d / 1000.0 for d in settings.rtsp_backoff_delays_ms]
  _FAILURE_THRESHOLD = settings.rtsp_failure_threshold
  ```
- [x] 6.3 Update CLAUDE.md §12 pitfall table:
  ```
  | RTSP failure handling | Configurable per site: `settings.rtsp_failure_threshold` (default 5) and `rtsp_backoff_delays_ms`. CLAUDE.md no longer cites a hardcoded number. |
  ```
- [x] 6.4 Add test `test_rtsp_threshold_reads_from_config` in test_ingestion_worker.py
- [x] 6.5 Commit: `feat(config): rtsp_failure_threshold and rtsp_backoff_delays_ms now configurable`

---

## Task 7: End-to-end full-pipeline integration test (D9)

**Background:** No test proves contract integrity across all modules. Inter-module
contract drift surfaces in production.

### Subtasks

- [x] 7.1 Create `tests/test_e2e_full_pipeline.py`
- [x] 7.2 Synthetic frame source: a small helper that pushes pre-generated frames
  (numpy arrays with one synthesized face) into the `frames:group1` Redis stream
  with proper `FramePointer` headers, no cv2 capture
- [x] 7.3 Test 1: `test_e2e_known_person_no_unknown_alert`:
  - Seed DB with one Person + one PersonEmbedding (a known vector)
  - Start IngestionWorker (synthetic source), InferenceEngine, IdentityEngine,
    DBWriter, AnomalyOrchestrator with `UnknownPersonDetector`
  - Push 10 frames containing the seeded face
  - Wait up to 5s for pipeline to drain
  - Assert: zero `UNKNOWN_PERSON` alerts in `alerts` table
  - Assert: at least one TrackingEvent row with non-null `person_id`
- [x] 7.4 Test 2: `test_e2e_unknown_person_fires_alert`:
  - Same setup, push 10 frames containing a face that doesn't match the seed
  - Assert: at least one `UNKNOWN_PERSON` alert in `alerts` table with `state='active'`
  - Assert: AnomalyEvent FSM transitioned through PENDING → FIRED
- [x] 7.5 Mark tests `@pytest.mark.integration` so they run on `main` branch only
- [x] 7.6 Document required fixtures in `tests/conftest.py`: real test PostgreSQL
  on port 5434, real Redis on port 6380 (separate from dev Redis)
- [x] 7.7 Verify: full suite still completes in <60s for unit tests, <90s with
  integration tests
- [x] 7.8 Commit: `test: add end-to-end full-pipeline integration test`

---

## Task 8: Phase 3 plan placeholder — system_health alerting + data retention (D2 + D3)

**Background:** D2 (system health) and D3 (data retention) are Phase 3 / Phase 5
scope additions. Capture the scope decisions now so the plans, when written, have
the rationale.

### Subtasks

- [x] 8.1 Create `docs/superpowers/plans/PHASE3-SCOPE-ADDITIONS.md` (a stub, not a
  plan):
  ```markdown
  # Phase 3 — Additional scope captured 2026-05-27

  ## SYSTEM_HEALTH alert channel (from /plan-eng-review D2)

  - New alert_type values: CAMERA_DOWN, FAISS_STALE, SCHEDULER_STALLED,
    DISK_HIGH, INFERENCE_LAG_HIGH
  - Two new detector classes: CameraHealthDetector, ServiceHealthDetector
  - Reuses existing AlertDispatcher; new alert_routing rules target ops role
    instead of security role
  - Operators see system alerts in a separate dashboard tab (Phase 4)

  ## Reason
  Anomaly framework alerts only on people-events. Silent system failures (camera
  drops, FAISS staleness, scheduler stalls) currently produce no alerts.
  See decision log D2 in 2026-05-27-vms-foundation-hardening-and-docs-cleanup.md.
  ```
- [x] 8.2 Create `docs/superpowers/plans/PHASE5-SCOPE-ADDITIONS.md` stub:
  ```markdown
  # Phase 5 — Additional scope captured 2026-05-27

  ## Configurable per-table data retention (from /plan-eng-review D3)

  - tracking_events: default 90 days, monthly partitioning, drop oldest partition
  - alerts: default 1 year
  - person_clip_embeddings: default 30 days (matches forensic search window)
  - audit_log: default 7 years (legal retention)
  - All retention values configurable via Settings; per-customer override possible
  - Nightly prune job in vms.scheduler

  ## 24h soak / load test (from /plan-eng-review D10)

  - scripts/soak_simulate.py replays pre-recorded video files as 52 virtual cameras
  - Output: CSV of memory + latency + dropped-frame metrics over 24h
  - Validates v2 spec §K capacity claims before any sales conversation
  - Acceptance criteria: stable memory (no growth > 5% over 24h), p99 latency
    within spec, dropped-frame rate < 0.1%

  ## Reason
  See decision log D3 + D10 in 2026-05-27-vms-foundation-hardening-and-docs-cleanup.md.
  ```
- [x] 8.3 Commit: `docs: stub Phase 3 and Phase 5 scope additions from foundation hardening review`

---

## Task 9: Final pass — verify nothing broken

- [x] 9.1 `ruff check vms/ tests/` clean
- [x] 9.2 `mypy vms/` clean
- [x] 9.3 `pytest tests/ -q` — all existing 159 tests still pass + new E2E test passes
- [x] 9.4 `grep -r 'phase1-foundation' docs/ CLAUDE.md` returns zero (link rot check)
- [x] 9.5 `grep -r 'main.py\|face_detection.py\|enrollment_emp.py\|face_utils.py\|scrfd_face.py' --include='*.md' --include='*.py' vms/ docs/ CLAUDE.md` returns zero unintended references
- [x] 9.6 Confirm CLAUDE.md §3 phase status section reflects all subphase renames
- [x] 9.7 Confirm production-readiness spec is linked from CLAUDE.md
- [x] 9.8 Commit: `chore: final foundation-hardening verification`

---

## Execution order

```
Task 2 (tidy)         ──┐
Task 3 (rename)       ──┼─→ Task 9 (verify)
Task 6 (config)       ──┤
Task 7 (E2E test)     ──┘

Task 1 (readiness spec) ─┐
Task 4 (runbooks)     ──┼─→ Task 9 (verify)
Task 5 (onboarding)   ──┤
Task 8 (scope stubs)  ──┘
```

Lane A (code-touching): Task 2, 3, 6, 7 — sequential because they all touch CLAUDE.md
Lane B (docs-only): Task 1, 4, 5, 8 — parallel-safe

Recommendation: do Lane B in parallel worktrees; Lane A serially. Then Task 9.

---

## NOT in scope (deferred elsewhere)

- System health alerts implementation — Phase 3 (stub captured in Task 8)
- Data retention implementation — Phase 5 (stub captured in Task 8)
- 24h soak test — Phase 5 (stub captured in Task 8)
- Phase 4 onboarding wizard UI — Phase 4 (runbook from Task 5 is the spec)
- Phase 1A.2 + Phase 1B.2 hardening implementation — separate plans split out by Task 3
- Phase 2b anomaly framework implementation — separate plan, reviewed clean

---

## What already exists (reused, not rebuilt)

- `docs/EXPLAINER.md` — customer pitch; no change needed
- `CLAUDE.md` — updated in Tasks 2, 3, 6; not rewritten
- Existing specs — referenced by readiness spec; not modified
- AlertDispatcher (Phase 3 implementation) — reused for system_health channel
- vms.scheduler (Phase 5) — reused for nightly prune job
- Existing test infrastructure (real PG + Redis fixtures) — reused for E2E test

---

## Self-Review Checklist

- [x] D1 production readiness spec — Task 1
- [x] D2 system health channel — Task 8 (Phase 3 stub) + production-readiness spec gates
- [x] D3 data retention — Task 8 (Phase 5 stub) + production-readiness spec gates
- [x] D4 four ops runbooks — Task 4
- [x] D5 customer onboarding — Task 5
- [x] D6 legacy/ + delete superseded plan — Task 2
- [x] D7 subphase rename — Task 3
- [x] D8 config-driven RTSP threshold — Task 6
- [x] D9 E2E full-pipeline test — Task 7
- [x] D10 soak test deferred — Task 8 (Phase 5 stub)
- [x] No new business logic; foundation cleanup only
- [x] Each task has a single git commit
- [x] No magic numbers introduced; config used where applicable
- [x] All decisions traceable to D1-D10 in the decision log

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 10 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**UNRESOLVED:** 0

**VERDICT:** ENG CLEARED — 10 cascading-failure risks surfaced and resolved into 9
discrete tasks. Ready to implement. CEO Review optional for sales positioning (D1
production-readiness spec touches commercial scope).
