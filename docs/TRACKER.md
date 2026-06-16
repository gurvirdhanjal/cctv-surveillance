# VMS Project Tracker

_Last updated: 2026-06-15 · Update this file after every significant work session._

---

## Current Status

| Item | Value |
|---|---|
| **Active phase** | Phase 3 complete — next: ReID Quality Hardening |
| **Next plan** | `docs/superpowers/plans/2026-06-15-vms-phase3-reid-quality-hardening.md` |
| **Tests passing** | 473 (5 deselected — heavy_models) |
| **Branch** | `feat/phase-2b-anomaly-framework` |
| **Frontend** | Deferred — starts after Phase 3 backend is complete |

---

## Open Gaps (must close before Phase 4)

These are confirmed missing vs. spec. Each needs a plan checkbox before implementation starts.

| Gap | Spec ref | Status |
|---|---|---|
| `GET /api/forensic/search` + `GET /api/forensic/clips/{id}` | §F.2 | Not started — needs CLIP embedding pipeline |
| `GET /api/audit/verify` + `GET /api/audit/export` | §F.3 | Not started — AuditLog + hash chain exist, no route |
| `GET /api/sites/readiness-report.pdf` | §B | In plan — `2026-06-13-vms-phase3-camera-profiler.md` Task 7 |
| Body Re-ID upgrade: TransReID-SSL ViT-B/16 MSMT17 supervised checkpoint | Phase 6 | Deferred — SSL backbone only downloaded; no ID head |
| `adaface_min_sim=0.72` re-calibration on real footage | — | Deferred — mandatory /advisor before changing |
| PDF export unsigned (no digital signature) | §F.3 | Deferred — needs crypto signing spec |
| ONVIF night-mode IR re-sample | §B | Deferred to Phase 6 |
| Gallery health: dedup consolidation + pruning job | Phase 3 | Deferred — enrollment-only dedup is current guard |

---

## Next Tasks (in order)

1. **ReID Quality Hardening** — plan written, not started
   - (A) Hybrid crop quality gates + pre-norm embedding norm signal
   - (B) Temporal quality-windowed gallery sub-sampling
   - (C) Enrollment cosine-dedup check ← DONE in commit `02645735`
2. **Camera Profiler** — plan written (`2026-06-13-vms-phase3-camera-profiler.md`), not started
3. **Audit routes** (`/api/audit/verify`, `/api/audit/export`) — no plan yet
4. **Phase 4: Frontend** — blocked until Phase 3 backend complete

---

## Phase History

| Phase | Tests | Commit | Date |
|---|---|---|---|
| Phase 3 Alert Dispatcher | 473 | `b4981d8f` | 2026-06-06 |
| PPE Compliance | 405 | — | 2026-06-06 |
| Phase 2d Multi-Modal Tracking | 372 | — | 2026-05-31 |
| Phase 2c Cross-Camera Hardening | 342 | — | 2026-05-31 |
| Phase 2b Anomaly Framework | 306 | — | 2026-05-15 |
| tracking_events Partitioning | 227 | — | 2026-05-28 |
| Storage Abstraction | 219 | — | 2026-05-28 |
| Foundation Hardening | 176 | `3bd6669` | 2026-05-27 |
| Phase 2a.2 Hardening | 159 | `019e45e` | 2026-05-14 |
| Phase 2a.1 Identity Framework | 128 | `634c8c4` | 2026-05-14 |
| Phase 1B.1 Ingestion/Inference | 96 | `019e45e` | 2026-05-09 |
| Phase 1A.1 DB Schema + Scaffold | 57 | `4a4bc49` | 2026-05-01 |

Full delivery details: `docs/superpowers/notes/PHASE-HISTORY.md`

---

## Key Technical Gotchas (quick-ref)

| Item | Value |
|---|---|
| SCRFD output | 9 outputs, pre-sigmoid, letterbox resize, single `det_scale` |
| AdaFace preprocessing | BGR→RGB, `(pixel - 127.5) / 127.5`, 5-point affine alignment |
| `assign_and_identify()` | Returns 3-tuple `(gid, person_id, resolved_via)` — all three must be persisted |
| Body Re-ID threshold | `reid_body_confirmed_sim=0.51` — do not adjust without re-running sim |
| Alert dispatcher cursor | `dispatcher:alerts:cursor` in Redis — do not rename |
| PPE class indices | helmet=10, vest=16, gloves=9, mask=5 |
| DB timestamps | Always `datetime.now(timezone.utc).replace(tzinfo=None)` — never `utcnow()` |
| FAISS is derived | Rebuild from `person_embeddings` on startup; never treat as primary store |
