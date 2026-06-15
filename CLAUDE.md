# CLAUDE.md — VMS Project Memory

You are working on a plant-floor **Video Management System** with facial recognition, cross-camera tracking, head counting, and anomaly detection (intrusion, violence, loitering). The system targets manufacturing customers running their **existing IP cameras** — smart cameras are an optional upgrade. It runs on-premises on a single GPU server (52-camera v1 deployment; horizontally scalable).

This file is read before every task. It encodes the binding rules of this project — read it, then read the spec.

---
## 0. Behavioral Guidelines

### 0.1 Think Before Coding
Before implementing: state assumptions explicitly. If uncertain, ask.
If multiple interpretations exist, present them — don't pick silently.
If something is unclear, stop and name what's confusing.

### 0.2 Simplicity First
Minimum code that solves the problem. No features beyond what was asked.
No abstractions for single-use code. No unrequested configurability.
If you write 200 lines and it could be 50, rewrite it.

### 0.3 Surgical Changes
Touch only what you must. Don't improve adjacent code.
Match existing style. Remove only imports/variables YOUR changes made unused.
Every changed line should trace directly to the request.

### 0.4 Goal-Driven Execution

Before writing any code for a task involving an API route:

**Pre-task checklist:**
- [ ] Open the spec section for this route
- [ ] List all endpoints the spec defines for that section
- [ ] Confirm which exist in the route file and which are missing
- [ ] If missing endpoints exist: implement them in this task OR create explicit
      sub-tasks for them before marking the parent done

Then transform tasks into verifiable goals and state a brief plan with verify steps:
  1. [Step] → verify: [check]
  2. [Step] → verify: [check]

### 0.5 Escalation — When Stuck, Use /advisor

When you hit any of the following, **stop and invoke `/advisor` before writing code**:

- Architecture trade-offs with no clear winner (e.g. two valid DB designs)
- Spec contradictions that can't be resolved by reading the hierarchy in §1
- Complex concurrency, partitioning, or security design decisions
- A bug whose root cause isn't clear after two attempts
- Any decision where getting it wrong means a migration or breaking change

**How `/advisor` works:**
`/advisor` spawns a Claude Opus 4.8 agent with full project context and your specific
question. Opus has deeper reasoning than Sonnet and is the right tool for hard decisions.
It returns a recommendation you can either accept or push back on — you stay in control.
**Invocation in Claude Code:** Use the `Skill` tool (`skill: 'advisor'`) if the skill is registered; otherwise use the `Agent` tool with `model: 'opus'`, pasting the question and the relevant spec excerpt into the prompt.

**Trigger phrase examples:**
- "I'm stuck on X, use /advisor"
- "/advisor — should we do A or B for the topology join?"
- "/advisor — this spec section contradicts the migration, what wins?"

**When NOT to use it:** Routine implementation, green-field tasks with a clear plan,
or anything the spec already answers. Overusing Opus burns tokens for no gain.

**MANDATORY /advisor — these are non-negotiable:**
- Schema migration touching non-empty production tables
- Changing identity matching thresholds (`reid_*`, `scrfd_conf`, `adaface_*`)
- Modifying cross-camera topology or spatial-temporal gate logic
- Any change touching `audit.py`, `compute_row_hash`, or `row_hash_version`
- Alembic `downgrade()` that drops columns or tables with data

### 0.6 Performance-sensitive paths

These execute on every frame — measure before introducing any per-frame DB query,
per-frame Redis round-trip, or O(n²) scan:
- `ingestion/worker.py` — camera → SHM → stream publish
- `inference/engine.py` — SCRFD + AdaFace + YOLO + BoT-SORT per frame
- `identity/` — FAISS search + FSM per detection
- `writer/db_writer.py` — flush_detection_frame batch

Prefer batching, async I/O, or pre-computed lookups. Target: ≤ 50 ms end-to-end per frame at 52 cameras.

## 1. Spec hierarchy — read this BEFORE writing any code

The design is split across multiple spec files. They are read together, not in isolation:

| File | Authority |
|---|---|
| `docs/superpowers/specs/2026-04-23-vms-facial-recognition-design.md` | v1 baseline. Sections marked "unchanged" in v2 are still authoritative |
| `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` | **v2 — the current source of truth.** Supersedes v1 for every section it touches. Includes scope, anomaly framework, maintenance windows, alert dispatcher, capacity model, model lifecycle, and 12 hardening items |
| `docs/superpowers/specs/2026-05-01-vms-db-edge-cases.md` | Companion to v2: every concurrency, cascade, partition, time, GDPR, and invariant rule the DB must enforce. Adds CHECK constraints + UNIQUE constraints to the migration |
| `docs/superpowers/specs/2026-05-01-vms-frontend-design.md` | Frontend source of truth: tech stack, three views (Guard / Management / Admin), state management, real-time integration, a11y, perf budgets |
| `docs/superpowers/specs/2026-05-27-vms-production-readiness.md` | **v1 GA acceptance spec.** Exit criteria, SLOs, security/GDPR/ops gates, capacity claims, per-phase gate-closing matrix |
| `docs/superpowers/specs/2026-05-28-vms-storage-scalability.md` | **Storage scalability spec.** StorageBackend Protocol (local/MinIO), `tracking_events` monthly partitioning, three-tier scaling roadmap |
| `docs/superpowers/specs/2026-06-12-vms-recording-clips-analytics.md` | **Recording, alert clips & analytics spec (Draft, not yet planned).** Pluggable `RecordingBackend` (FFmpeg HLS remux), alert clip + live + forensic playback API, PostgreSQL rollup analytics. Target Phase 3 |
| `docs/superpowers/specs/2026-06-13-vms-gpu-acceleration.md` | **GPU acceleration spec (Draft, not yet planned).** ONNX Runtime TensorRT EP (FP16/INT8), model-format normalization to ONNX, NVDEC decode, Triton cross-camera batching, multi-GPU sharding, DeepStream go/no-go. Extends v2 §G capacity model. Target Phase 6 |

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
legacy/                  # Pre-Phase 1A prototype code — DO NOT IMPORT (see below)
models/                  # Downloaded ML models (not committed; see §8)
docs/                    # Specs, plans, presentations — see §16 for layout convention
tests/                   # Pytest suite — mirrors vms/ structure
scripts/                 # CLI tools, fine-tune recipes (Phase 5)
```

Legacy prototype code is in `legacy/`. Do not import.

---

## 3. Current phase

### Known open gaps (from 2026-06-12 audit)

These are spec-required items confirmed missing in the live codebase. Each must have
a plan checkbox before Phase 4 starts. No implementation without an approved plan.

| Gap | Spec ref | Notes |
|---|---|---|
| ~~`POST /PATCH /DELETE /api/maintenance` + calendar endpoint~~ | §D | **DONE** — commits `1d94c8fe`, `f24c1257`, `dffcad7e`, `88e9e686` |
| ~~`PATCH /api/anomaly-detectors/{id}` (enable/disable, update config)~~ | §C | **DONE** |
| ~~`PATCH /api/alert-routing/{id}`~~ | §E | **DONE** — commit `ad85adfe` |
| `GET /api/forensic/search` + `GET /api/forensic/clips/{id}` | §F.2 | Needs CLIP embedding pipeline; DB table exists |
| `GET /api/audit/verify` + `GET /api/audit/export` | §F.3 | AuditLog table + hash-chain exist; no route |
| ~~`POST /api/cameras/{id}/recalibrate-required`~~ | §H.3 | **DONE** — `recalibrate_required_at` column + migration `a1b2c3d4e5f7` + route |
| `GET /api/sites/readiness-report.pdf` | §B | **IN PLAN** — `2026-06-13-vms-phase3-camera-profiler.md` Task 7 |
| ~~`alert_dispatcher_retry_delays_s` + `alert_dispatcher_max_attempts` in `config.py`~~ | §17 invariants | **DONE** — in `config.py`; hardened plan `2026-06-13-vms-phase3-hardening.md` |
| PDF export is unsigned (no digital signature) | §F.3 | Spec says "signed PDF" — deferred; needs crypto signing spec before implementation |
| ONVIF night-mode probe (IR re-sample for brightness re-test) | §B | Deferred — no ONVIF library in requirements; add to Phase 6 camera rollout plan |
| ~~`_emit_critical_alert` in scheduler reuses `alert_type='UNKNOWN_PERSON'`~~ | §M | **DONE** — uses `SYSTEM_CRITICAL` + `camera_id=None`; migration `f1a2b3c4d5e6`; Guard view filters it; scheduler plan updated |

---

**Active:** Phase 3 Alert Dispatcher — **COMPLETE** (473 tests, commit `b4981d8f`). Plan: `docs/superpowers/plans/2026-06-06-vms-phase3-alert-dispatcher.md`.

**Last major milestone:** All Phase 2 sub-phases complete (2a Identity, 2b Anomaly, 2c Cross-Camera Hardening, 2d Multi-Modal Tracking, PPE Compliance).

**Next:** Camera Profiler + Audit hardening (Phase 3 remaining) — **no plan written yet.** Do not begin without an approved plan file. See §4.1.

**Rule:** Never start a phase without an approved plan file in `docs/superpowers/plans/`. Each phase gets exactly one plan file; do not start implementation before the plan is reviewed.

**Key technical gotchas (quick reference):**
- PPE model SH17 class indices: helmet=10, vest=16, gloves=9, mask=5. Activate: `VMS_PPE_MODEL=models/sh17_ppe_yolov8l.onnx`.
- `assign_and_identify()` returns a 3-tuple `(gid, person_id, resolved_via)` — all three must be persisted; discarding `resolved_via` silently degrades identity audit data.
- Body Re-ID threshold: `reid_body_confirmed_sim=0.51` (calibrated from simulation — do not adjust without re-running sim).
- Alert Dispatcher cursor key: `dispatcher:alerts:cursor` in Redis — do not rename without updating worker.py.
- **SCRFD_10G_KPS** (`models/scrfd_10g_bnkps.onnx`): 9-output model (confirmed). Outputs are **pre-sigmoid** — do NOT apply sigmoid in `_decode`. Uses **letterbox resize** (not stretch) with single `det_scale`. End-to-end verified 2026-06-15.
- **AdaFace embedder preprocessing**: input must be **BGR** (do NOT convert to RGB — the model was trained on BGR). Normalization is `(pixel - 127.5) / 127.5` (not 128.0). 5-point affine alignment active when SCRFD_10G_KPS keypoints are present.
- **`adaface_min_sim=0.72` needs re-calibration** — threshold was set for unaligned bbox-crop embeddings. Affine-aligned embeddings have a different distribution. Re-run calibration on real footage before raising this threshold.
- **`vit_base_ics_cfs_lup.pth`** = TransReID-SSL **SSL backbone only** (88.4M params, ViT-B/16+ICS, 256×128 input). No BNNeck, no classifier head, no identity labels. NOT deployable as body Re-ID without supervised fine-tuning. Do not swap into `body_embedder.py`.
- **Body Re-ID Phase 6 upgrade target**: `ViT-B/16+ICS supervised on MSMT17` from TransReID-SSL repo (75.1 mAP / 89.6 R1). Requires: timm==0.3.4 env, ONNX export script, new `TransReIDBodyEmbedder` class, re-calibration of `reid_body_confirmed_sim`. **Do NOT use DukeMTMC** (dataset officially retracted — legal risk).
- **BoT-SORT GMC note**: Python-mode `--cmc-method orb` available for camera-vibration ID-switch reduction. Not needed for fixed plant-floor cameras. Phase 6 tuning option only.

Full completed phase delivery details: `docs/superpowers/notes/PHASE-HISTORY.md`.

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

### 4.5 Spec coverage is verified before marking a task complete

For every route file touched in a task:
1. Open the relevant spec section
2. List every endpoint the spec defines for that section
3. Confirm each one exists in the route file
4. If any are missing: either implement them in this task OR create a tracked
   sub-task before marking the parent done

"Deferred to later" is only valid if a new plan checkbox exists for the deferred
item. Silent deferral — checking a task done while endpoints are still missing —
is not allowed.

### 4.4 Operational priority order

When a trade-off has no clear answer, use this order:
1. Never lose tracking events (data durability above all)
2. Never misidentify a person (identity correctness)
3. Never break audit integrity (hash chain + append-only)
4. Maintain real-time throughput (≤ 50 ms/frame)
5. Developer ergonomics (last)

---

## 5. Coding standards

Python style is documented in the user's `~/.claude/rules/python-coding-style.md` and `python-patterns.md`. Project-specific additions:

- **Type annotations everywhere.** `mypy --strict` must pass. `Any` requires a comment explaining why.
- **Frozen dataclasses for DTOs**, especially in inter-module messages (between ingestion → inference → identity). Mutability is opt-in via `@dataclass(frozen=False)` and must be justified.
- **No `print()` calls in production code.** Use `logging.getLogger(__name__)`.
- **Timezone convention:** DB stores all timestamps as UTC-naive (`TIMESTAMP WITHOUT TIME ZONE`). In code, always use `datetime.now(timezone.utc).replace(tzinfo=None)` — never bare `datetime.utcnow()`. Developer timezone is **IST (UTC+5:30)** for notes and plan dates; this does not affect DB or API behaviour.
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
11. If the change adds or modifies a route file: every endpoint listed in the spec
    section for that route exists and has at least one positive + one negative test.
    A route file with fewer endpoints than the spec = NOT DONE.
12. If a plan task is checked ✓: the check means ALL spec endpoints for that task
    exist, not just the minimum-viable ones. If full CRUD was deferred, the checkbox
    must be split into sub-tasks — one per endpoint — before the parent is marked done.

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
| Using `datetime.utcnow()` or bare `datetime.now()` | Both are wrong. Use `datetime.now(timezone.utc).replace(tzinfo=None)`. CI lint must flag both in `vms/` — neither form is acceptable |
| Calling `assign_and_identify()` and discarding the third return value | `resolved_via` must be written to `tracking_events.resolved_via` — silent discard causes identity audit gaps with no error raised |
| Storing a string longer than the column allows | Use Pydantic schemas at the API boundary; SQLAlchemy will silently truncate on some dialects |
| Logging an embedding tensor | Logger filter `vms.security.logging.SensitiveFilter` (Phase 5) blocks bytes/numpy values. Until then: pre-flight check in code review |
| Hard-coded thresholds (e.g. `if conf < 0.6`) | Use `get_settings().scrfd_conf`. Per-camera overrides via `cameras.model_overrides` |
| Forgetting to publish `faiss_dirty` after a person enrol/purge | FAISS goes stale. Use the `vms.identity.faiss_dirty.publish_<action>` helper which enforces this |
| Editing a published Alembic migration | Never. Write a new migration that corrects |
| Bundling an ONNX file in a commit | Use `models/manifest.json` + `vms-models download` |
| Leaving `print()` calls | Replace with `logger.<level>(...)`. CI lint catches these |
| Hardcoded retry/timeout/threshold values | Every tunable numeric constant belongs in `vms/config.py` as a `VMS_*` env var. Search for bare numeric literals in non-test code before marking any task done. Current known violation: `_DEFAULT_RETRY_DELAYS` and `_MAX_ATTEMPTS` in `dispatcher/worker.py` — tracked in §3 Known Gaps |

---

## 13. When in doubt

- **Read the spec first.** Most ambiguity disappears once you've read the relevant section.
- **Check the edge-cases spec for anything DB-related.** Especially before adding a new table or constraint.
- **Ask the user before destructive actions** — deleting files, dropping tables, force pushes, schema rollbacks. The user's git rules forbid silent destructive ops.
- **If a memory in `~/.claude/projects/D--facial-recognistion/memory/` conflicts with the spec or CLAUDE.md, prefer the spec.** Memories are point-in-time observations; specs and CLAUDE.md are durable.
- **Before writing a Phase N plan:** run a spec-vs-code gap check for all routes touched in Phase N-1. List any missing endpoints in the Known Gaps table in §3 before the new plan is written. This takes 10 minutes and prevents audit findings like the June 2026 one.

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
│   ├── specs/       YYYY-MM-DD-vms-<topic>.md               ← design specifications
│   ├── plans/       YYYY-MM-DD-vms-<phase>-<topic>.md        ← implementation plans
│   └── notes/       YYYY-MM-DD-vms-<phase>-implementation-notes.md ← task notes
└── EXPLAINER.md                                               ← standalone reference docs
```

### Naming rules

| Type | Pattern | Example |
|---|---|---|
| Design spec | `YYYY-MM-DD-vms-<topic>.md` | `2026-05-01-vms-v2-hardened-design.md` |
| Implementation plan | `YYYY-MM-DD-vms-<phase>-<topic>.md` | `2026-05-09-vms-v2-phase1b-ingestion-inference-api.md` |
| Implementation notes | `YYYY-MM-DD-vms-<phase>-implementation-notes.md` | `2026-05-09-vms-v2-phase1b-implementation-notes.md` |
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

### Implementation notes

Each phase also gets one notes file in `docs/superpowers/notes/`. Update the notes file after each task completes — record decisions made, fixes applied, and anything surprising. The notes file is the companion to the plan: the plan says what to do; the notes say what actually happened and why.

---

## 17. Architectural Invariants

The following may not be changed without a design review and explicit user approval:

| Invariant | Rule |
|---|---|
| PostgreSQL is source of truth | FAISS, Redis, caches are derived — DB wins on any conflict |
| FAISS is a derived cache | Rebuilt from `person_embeddings` on startup; never treated as primary |
| Redis Streams are the inter-service bus | No direct cross-module calls; ingestion → inference → identity → writer |
| DB write before FAISS update | Embedding committed to DB before FAISS is mutated |
| Audit log is append-only | No UPDATE/DELETE on `audit_log`; always write via `write_audit_event()` |
| Identity resolution order | Face ≻ Body ≻ BLE — owned by `FusionResolver`; don't shortcut |
| Topology gates cross-camera merges | `CameraTopology` must pass before any cross-camera identity join |
| Thresholds live in config | Never hard-code similarity or confidence values — use `get_settings()` |
| Scheduler owns all cron jobs | No ad-hoc `threading.Timer` or fire-and-forget `asyncio.create_task` loops for timed/recurring work — use the scheduler process exclusively (Phase 3) |

---

**End of CLAUDE.md.**
