# CLAUDE.md — VMS Project Memory

You are working on a plant-floor **Video Management System** with facial recognition, cross-camera tracking, head counting, and anomaly detection (intrusion, violence, loitering). The system targets manufacturing customers running their **existing IP cameras** — smart cameras are an optional upgrade. It runs on-premises on a single GPU server (52-camera v1 deployment; horizontally scalable).

This file is read before every task. It encodes the binding rules of this project — read it, then read the spec.

---

## 1. Spec hierarchy — read this BEFORE writing any code

The design is split across multiple spec files. They are read together, not in isolation:

| File | Authority |
|---|---|
| `docs/superpowers/specs/2026-04-23-vms-facial-recognition-design.md` | v1 baseline. Sections marked "unchanged" in v2 are still authoritative |
| `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` | **v2 — the current source of truth.** Supersedes v1 for every section it touches. Includes scope, anomaly framework, maintenance windows, alert dispatcher, capacity model, model lifecycle, and 12 hardening items |
| `docs/superpowers/specs/2026-05-01-vms-db-edge-cases.md` | Companion to v2: every concurrency, cascade, partition, time, GDPR, and invariant rule the DB must enforce. Adds CHECK constraints + UNIQUE constraints to the migration |
| `docs/superpowers/specs/2026-05-01-vms-frontend-design.md` | Frontend source of truth: tech stack, three views (Guard / Management / Admin), state management, real-time integration, a11y, perf budgets |

When the v1 and v2 specs disagree on an in-scope section, **v2 wins.** When the edge-cases spec adds a constraint that contradicts the migration in the Phase 1A plan, **the edge-cases spec wins** — update the migration to comply.

Plans (in `docs/superpowers/plans/`) are derived from specs. If a plan and its source spec disagree, fix the plan, not the spec.

---

## 2. Repository layout

```
vms/                     # Python package — production code (Phase 1A onward)
├── config.py            # pydantic-settings; reads VMS_* env vars
├── redis_client.py      # Phase 1B: Stream helpers (get_redis, stream_add, stream_read, stream_ack)
├── db/
│   ├── session.py       # engine, Base, SessionLocal, get_db
│   ├── models.py        # ALL ORM models (single file until ~600 lines)
│   └── audit.py         # hash-chain writer for audit_log — only public API: write_audit_event
├── ingestion/           # Phase 1B: camera → SHM → Redis Streams
│   ├── messages.py      # FramePointer frozen dataclass
│   ├── shm.py           # SHMSlot: header + BGR frame, staleness guard
│   └── worker.py        # IngestionWorker: camera loop + stream publish
├── inference/           # Phase 1B: SCRFD + AdaFace + YOLO/ByteTrack
│   ├── messages.py      # Tracklet, FaceWithEmbedding, DetectionFrame DTOs
│   ├── detector.py      # SCRFDDetector ONNX wrapper
│   ├── embedder.py      # AdaFaceEmbedder ONNX wrapper
│   ├── tracker.py       # PerCameraTracker (YOLO + ByteTrack)
│   └── engine.py        # InferenceEngine: reads frames stream → publishes detections
├── writer/              # Phase 1B: detections stream → tracking_events DB
│   └── db_writer.py     # DBWriter + flush_detection_frame (idempotent)
├── api/                 # Phase 1B+: FastAPI routes
│   ├── main.py          # FastAPI app + router registration
│   ├── deps.py          # get_db, get_current_user (JWT), create_access_token
│   ├── schemas.py       # Pydantic request/response models
│   └── routes/
│       ├── health.py    # GET /api/health
│       └── persons.py   # POST /api/persons · POST /api/persons/{id}/embeddings · GET /api/persons/search
├── identity/            # Phase 2 (re-id, FAISS, alert FSM)
├── anomaly/             # Phase 2 (AnomalyDetector interface + concrete detectors)
├── dispatcher/          # Phase 3 (alert delivery: email/slack/telegram/webhook)
├── profiler/            # Phase 3 (CameraProfiler + Site Readiness Report)
└── security/            # Phase 5: at-rest cipher, JWT helpers, sensitive log filter

alembic/                 # Database migrations — see §6
frontend/                # React SPA (Phase 4)
models/                  # Downloaded ML models (not committed; see §8)
docs/                    # Specs, plans, presentations — see §16 for layout convention
tests/                   # Pytest suite — mirrors vms/ structure
scripts/                 # CLI tools, fine-tune recipes (Phase 5)

# Legacy prototype files (DO NOT IMPORT, port patterns only):
main.py, face_detection.py, enrollment_emp.py, face_utils.py,
scrfd_face.py, test.py, test_db.py, config.py (root)
```

These legacy files are kept as reference until Phase 1B replaces them with the `vms.ingestion` and `vms.inference` modules. Do not edit, refactor, or import them.

---

## 3. Current phase

We are at **Phase 1B: Ingestion, Inference, and Base API.** See `docs/superpowers/plans/2026-05-09-vms-v2-phase1b-ingestion-inference-api.md` for the 10-task TDD plan.

**Phase 1A** (Database Schema, Project Scaffold, and Config) is **COMPLETE** — 57 tests passing as of commit `4a4bc49`. Plan: `docs/superpowers/plans/2026-05-01-vms-v2-phase1a-db-schema.md`.

Subsequent phases (Phase 2 Identity + Anomaly Framework, Phase 3 Profiler + Dispatcher + Audit, Phase 4 Frontend, Phase 5 Forensic + Hardening, Phase 6 Camera Rollout) each get their own plan file when started. **Do not start a phase before its plan exists and is approved.**

---

## 4. Working principles

### 4.1 Design-before-code is non-negotiable

Every non-trivial feature requires:
1. A spec section (or new spec) written and committed
2. A plan file with TDD tasks
3. Plan reviewed by user
4. Then implementation

If a user request would require new design, **stop and propose the design first** — even for "small" features. The phrase "this is too simple to need a design" is a code smell.

### 4.2 TDD is the default

For every feature task:
1. Write a failing test
2. Run it — confirm it fails for the expected reason
3. Implement the minimum to make it pass
4. Run it — confirm it passes
5. Refactor if needed
6. Commit

The Phase 1A plan demonstrates this rhythm. Maintain it.

### 4.3 Frequent commits

One logical change per commit. Conventional commit format:
```
<type>: <description>

<optional body>
```
Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`. **No AI co-author footer** (disabled globally via the user's `~/.claude/settings.json`).

---

## 5. Coding standards

Python style is documented in the user's `~/.claude/rules/python-coding-style.md` and `python-patterns.md`. Project-specific additions:

- **Type annotations everywhere.** `mypy --strict` must pass. `Any` requires a comment explaining why.
- **Frozen dataclasses for DTOs**, especially in inter-module messages (between ingestion → inference → identity). Mutability is opt-in via `@dataclass(frozen=False)` and must be justified.
- **No `print()` calls in production code.** Use `logging.getLogger(__name__)`.
- **No emoji or decorative characters in code or commit messages** — they break terminal rendering on some Windows shells.
- **Comments are rare.** Default to no comment. Only write a comment for non-obvious WHY (a hidden constraint, a workaround for a specific bug). Never comment what the code does — names should do that.
- **Files stay under ~600 lines.** When `vms/db/models.py` approaches that, split by domain (`models/identity.py`, `models/topology.py`, etc.) — but only when the threshold is hit, not preemptively.

Lint + format + type-check on every change:

```powershell
black vms/ tests/
ruff check vms/ tests/
mypy vms/
```

CI runs the same. Pre-commit hook recommended (Phase 1B may add this).

---

## 6. Database conventions — these are sacred

### 6.1 Schema changes go through Alembic

Never alter the schema with raw `CREATE TABLE` / `ALTER TABLE` outside of an Alembic migration. The migration file is the audit trail. If you change `vms/db/models.py`, you also write a new migration in the same commit.

```powershell
alembic revision -m "describe change"
# edit alembic/versions/<id>_describe_change.py
alembic upgrade head     # apply locally first
pytest tests/             # confirm tests still pass
```

### 6.2 Migration safety rules

- Each migration must define a working `downgrade()`. Test the round-trip locally before committing.
- For changes to populated tables (especially `tracking_events`), see `docs/.../db-edge-cases.md §11` for the maintenance-window protocol.
- Never re-edit a published migration. If a migration shipped to production is wrong, write a new one that fixes it.
- PostgreSQL-specific DDL (declarative partitioning, online index rebuild) uses `CREATE INDEX CONCURRENTLY` and `ATTACH PARTITION` syntax. Gate on phase if adding partitioning in Phase 5.

### 6.3 Idempotency is a writer-side responsibility

Every Redis-Streams consumer can be replayed. Database writers must:
- Use the unique constraint defined in the schema as the idempotency key (e.g., `tracking_events.uq_tracking_idem`)
- Use `INSERT ... ON CONFLICT DO NOTHING` (PostgreSQL) for idempotent retry
- Never assume a row was inserted by THIS attempt — it may have been by a previous, retried attempt

### 6.4 The audit log has special rules

- Audit rows are **immutable.** Never `UPDATE` or `DELETE` `audit_log` rows. Phase 5 adds a DB trigger that REJECTs both.
- Always write through `vms.db.audit.write_audit_event(...)`. Never construct an `AuditLog` ORM object directly. The helper enforces hash-chain linkage.
- The hash function is part of the API contract. **Do not change `compute_row_hash` without bumping `row_hash_version`** and documenting a chain-link breakpoint.

### 6.5 FAISS is a derived cache, not a source of truth

- The DB (`person_embeddings`) is authoritative. FAISS is rebuilt from it on identity-service startup.
- Mid-flight drift is reconciled by the `faiss_dirty` Redis Stream events. A nightly job detects drift > 5 vectors and triggers a rebuild.
- Never write to FAISS without a corresponding DB write committed first.

---

## 7. Security boundaries — never cross these

### 7.1 Authentication and authorisation

- **Every API endpoint requires authentication.** No endpoint exempt without explicit code review.
- **Role-based + zone/camera-level checks.** Even a `manager` role doesn't see cameras outside their `user_camera_permissions`. Check the permission, not just the role.
- JWT validation runs on every request via FastAPI dependency. Never `# type: ignore` an auth check.

### 7.2 Sensitive data handling

- **Never log embeddings.** They are biometric data. Log "embedding shape (512,)" not the values.
- **Never log RTSP URLs at INFO level.** They contain credentials. Log `camera_id` only.
- **Never log JWT tokens or password hashes.** Mask them in error responses too.
- **Face thumbnails on disk are encrypted at rest** (Phase 5). Until then, the directory must be on an encrypted volume — document this in the deploy runbook.

### 7.3 GDPR purge is irreversible

`DELETE /api/persons/{id}` blanks embeddings and scrubs thumbnails. **There is no undo.** The API requires:
- A typed confirmation matching the person's full name
- A reason string (audited)
- Admin role
- Audit log entry with `event_type='PERSON_PURGED'`

---

## 8. Models are not in the repo

ML model files (`*.onnx`, `*.pt`) are **never committed.** They are downloaded on first run from `models/manifest.json`:

```powershell
vms-models download           # fetch all + verify SHA-256
vms-models verify             # re-verify checksums
vms-models list               # show installed versions and per-camera overrides
vms-models pin <name> <ver>   # lock a specific version (writes to manifest.lock)
vms-models swap <name> <path> # register a fine-tuned ONNX
```

Adding `*.onnx` to `.gitignore` is mandatory. If you find a committed model file, remove it via `git rm` + open a follow-up to add it to the manifest.

---

## 9. Git rules — the absolute prohibitions

These come from the user's `~/.claude/rules/git-workflow.md` but are also enforced here:

### NEVER run any of these commands:

```
git reset --hard
git reset --hard HEAD
git reset --hard <ref>
git checkout -- .
git checkout -- <file>
git restore .
git restore <file>
git clean -f
git clean -fd
git clean -fdx
```

These commands have permanently destroyed the user's work in a previous session. There is no scenario in this project where they are the right tool.

### Commit/push protocol

When the user says "push", "commit", "save my work", or similar:

1. `git stash push -u -m "safe-push-backup-<timestamp>"` — safety snapshot FIRST
2. `git stash pop` — restore working tree (`--theirs` for any conflicts)
3. `git add -u` — tracked changes only (never `git add -A`)
4. `git commit` — conventional commit message
5. `git push origin HEAD`
6. Report commit hash + stash ref

Use the `/safe-push` skill if available — it bakes this protocol in.

### Pull requests

Never push directly to `main` without explicit user instruction. Create a feature branch + PR.

---

## 10. Testing standards

- **Coverage targets:** ≥ 80% on `vms/db`, `vms/config`, `vms/anomaly`, `vms/dispatcher`. ≥ 70% elsewhere.
- **Test naming:** `test_<unit-under-test>_<scenario>_<expected-outcome>`. e.g., `test_alert_fsm_dedup_window_suppresses_duplicate`.
- **Test ordering:** must not depend on order. Use `@pytest.fixture(autouse=True)` for setup; never share mutable state across tests.
- **Mark integration tests:** `@pytest.mark.integration`. CI runs unit tests on every commit, integration tests on `main` branch only.
- **One assertion per concept.** Multiple `assert` lines OK if they verify one logical claim.
- **No mocked DB in DB-layer tests.** Use a real PostgreSQL test instance (`pgvector/pgvector:pg16` on port 5434, container `vms-test-db`). Mocking the ORM defeats the purpose of testing it.
- **Frontend test patterns** are in the frontend design spec §18.

---

## 11. Definition of done

A task is done when ALL of these are true:

1. The associated test(s) pass: `pytest <path> -v`
2. The full test suite passes: `pytest`
3. Lint clean: `ruff check vms/ tests/`
4. Format applied: `black vms/ tests/`
5. Type-check clean: `mypy vms/` (strict)
6. Coverage at or above target: `pytest --cov=vms`
7. If the change affects schema: migration applied locally and round-trip tested
8. If the change affects API: endpoint tested with at least one positive + one negative test
9. Conventional commit created
10. Plan checkbox marked done

A task is **not** done when:
- Tests are partial or skipped
- Lint warnings remain
- "TODO" or "FIXME" added (these belong in tracked issues, not code)
- Tests pass but only because mocked behaviour matches mocked expectations (no real coverage)

---

## 12. Common pitfalls — read once, remember

| Pitfall | Mitigation |
|---|---|
| Running `Base.metadata.create_all` in a test before all referenced tables are defined → `NoReferencedTableError` | Define tables in dependency order; FK targets must be in metadata first. See Phase 1A plan Task 7 dependency note |
| Adding a new ORM model but forgetting the Alembic migration | Mandatory: every model change ships with a migration in the same commit |
| Calling `datetime.now()` instead of `datetime.utcnow()` | All timestamps are UTC. CI lint will flag `datetime.now()` calls in `vms/` |
| Storing a string longer than the column allows | Use Pydantic schemas at the API boundary; SQLAlchemy will silently truncate on some dialects |
| Logging an embedding tensor | Logger filter `vms.security.logging.SensitiveFilter` (Phase 5) blocks bytes/numpy values. Until then: pre-flight check in code review |
| Hard-coded thresholds (e.g. `if conf < 0.6`) | Use `get_settings().scrfd_conf`. Per-camera overrides via `cameras.model_overrides` |
| Forgetting to publish `faiss_dirty` after a person enrol/purge | FAISS goes stale. Use the `vms.identity.faiss_dirty.publish_<action>` helper which enforces this |
| Editing a published Alembic migration | Never. Write a new migration that corrects |
| Bundling an ONNX file in a commit | Use `models/manifest.json` + `vms-models download` |
| Leaving `print()` calls | Replace with `logger.<level>(...)`. CI lint catches these |

---

## 13. When in doubt

- **Read the spec first.** Most ambiguity disappears once you've read the relevant section.
- **Check the edge-cases spec for anything DB-related.** Especially before adding a new table or constraint.
- **Ask the user before destructive actions** — deleting files, dropping tables, force pushes, schema rollbacks. The user's git rules forbid silent destructive ops.
- **If a memory in `~/.claude/projects/D--facial-recognistion/memory/` conflicts with the spec or CLAUDE.md, prefer the spec.** Memories are point-in-time observations; specs and CLAUDE.md are durable.

---

## 14. Working with subagents

When dispatching a subagent (Plan, Explore, code-reviewer, etc.):
- Pass the exact spec section the subagent should reference.
- Do not delegate understanding — synthesise findings yourself before deciding.
- For Phase 1A tasks: prefer subagent-driven execution (one subagent per task, review the diff between tasks). The Phase 1A plan calls this out at the bottom.

---

## 15. Outside this file

- User's global rules: `~/.claude/rules/{python-*,git-workflow,development-workflow,performance,agents}.md`
- User's global memory for this project: `~/.claude/projects/D--facial-recognistion/memory/MEMORY.md`
- User email: `ai@apltechno.com`. User git name: `Gurvir Singh`.

---

## 16. Documentation layout — uniform convention

All project documentation lives under `docs/`. The directory tree and naming rules below apply to every new file added.

```
docs/
├── superpowers/
│   ├── specs/       YYYY-MM-DD-vms-<topic>.md       ← design specifications
│   └── plans/       YYYY-MM-DD-vms-<phase>-<topic>.md ← implementation plans
└── EXPLAINER.md                                       ← standalone reference docs
```

### Naming rules

| Type | Pattern | Example |
|---|---|---|
| Design spec | `YYYY-MM-DD-vms-<topic>.md` | `2026-05-01-vms-v2-hardened-design.md` |
| Implementation plan | `YYYY-MM-DD-vms-<phase>-<topic>.md` | `2026-05-09-vms-v2-phase1b-ingestion-inference-api.md` |
| Reference / explainer | `<topic>.md` under `docs/` root | `EXPLAINER.md` |

### Required header for every plan

Every plan file must start with:

```markdown
# <Title> Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: NOT STARTED | IN PROGRESS | COMPLETE**

**Goal:** ...

**Architecture:** ...

**Tech Stack:** ...

**Spec refs:** ...
```

### Required header for every spec

```markdown
# <Title>
**Design Specification** · YYYY-MM-DD
**Status:** Draft | Approved | Superseded
```

### Plan status tracking

Update the `**Status:**` line in the plan file as work progresses:
- `NOT STARTED` → plan written, not yet executing
- `IN PROGRESS` → execution under way; note current task number
- `COMPLETE` → all tasks done, tests passing, committed

Also update CLAUDE.md §3 to reflect which phase is active.

### One plan per phase

Each phase gets exactly one plan file. A plan that grows unwieldy (> 800 lines) should be split into sub-phase plans (`phase2a`, `phase2b`, etc.). Sub-phase plans follow the same naming convention.

---

**End of CLAUDE.md.**
