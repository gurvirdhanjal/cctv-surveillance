# VMS Production Readiness Specification
**Design Specification** · 2026-05-27 · **Last updated: 2026-06-01**
**Status:** Approved

This document enumerates the exit criteria for a v1 GA ("sellable") deployment.
Each gate names a criterion, the phase that delivers it, evidence required, and current status.

---

## 1. Service Level Objectives

| SLO | Target | Measurement | Status |
|---|---|---|---|
| API uptime | 99.5% / month (planned maintenance excluded) | Uptime probe every 60s | Phase 3 |
| Frame ingestion latency p50 | < 50 ms (camera → SHM) | Worker timestamp delta | Phase 1B.1 ✓ |
| Frame ingestion latency p99 | < 200 ms | Worker timestamp delta | Phase 1B.1 ✓ |
| Inference latency p50 | < 150 ms per frame (SCRFD + AdaFace) | InferenceEngine timing | Phase 1B.1 ✓ |
| Alert dispatch latency p99 | < 5 s from anomaly detection to webhook/email | Dispatcher timestamp delta | Phase 3 |
| FAISS staleness ceiling | ≤ 5 vectors stale vs DB | Nightly drift check | Phase 2a.1 ✓ |
| DB write throughput | ≥ 52 cameras × 25 fps × per-frame row | Benchmark on target HW | Phase 5 |

---

## 2. Security Audit Gates

| Gate | Criterion | Phase | Evidence | Status |
|---|---|---|---|---|
| OWASP Top 10 | All 10 categories reviewed; no criticals | Phase 5 | Security review report | Pending |
| Dependency CVE scan | `pip-audit` clean or all highs suppressed with justification | Phase 5 | `pip-audit` output | Pending |
| JWT handling | Tokens expire ≤ 8h; refresh flow tested; `jwt_secret` never logged | Phase 1B.1 ✓ | Code review | Done |
| Secrets management | No secrets in repo; `.env` documented; RTSP creds masked in logs | Phase 1B.1 ✓ | Grep check | Done |
| RTSP credential redaction | RTSP URLs not logged at INFO; `camera_id` logged instead | Phase 1B.1 ✓ | Log sample | Done |
| At-rest encryption | Face thumbnails on encrypted volume; DB at-rest optional | Phase 5 | Deploy runbook | Pending |
| Role-based access | All endpoints require auth; manager role zone-scoped | Phase 1B.1 ✓ | Auth tests | Done |

---

## 3. GDPR Audit Gates

| Gate | Criterion | Phase | Evidence | Status |
|---|---|---|---|---|
| Data inventory | All PII tables documented: `persons`, `person_embeddings`, `audit_log`, thumbnails | Phase 1A.1 ✓ | DB schema | Done |
| Retention policy | Configurable per-table retention with defaults; nightly prune job | Phase 5 | `PHASE5-SCOPE-ADDITIONS.md` | Pending |
| Purge procedure | `DELETE /api/persons/{id}` blanks embeddings, unlinks thumbnails, writes audit event | Phase 1B.2 ✓ | Purge tests | Done |
| Audit log immutability | `audit_log` rows never updated/deleted; hash chain verified on restore | Phase 1A.1 ✓ | DB trigger (Phase 5); tests | Partial |
| Right-to-access export | API endpoint returns all person data as JSON | Phase 3 | Endpoint + test | Pending |
| Consent / lawful basis | Documented per customer in onboarding runbook | Phase 4 | Onboarding doc | Partial |

---

## 4. Operational Gates

| Gate | Criterion | Phase | Evidence | Status |
|---|---|---|---|---|
| Install runbook | Step-by-step tested on fresh Ubuntu 22.04 VM | Foundation ✓ | `docs/runbooks/install.md` + tester sign-off | Doc done |
| Upgrade runbook | Zero-downtime blue/green documented | Foundation ✓ | `docs/runbooks/upgrade.md` + tester sign-off | Doc done |
| Backup proven | `pg_dump` + restore verified on test data | Foundation ✓ | `docs/runbooks/backup-restore.md` + DR drill | Doc done |
| DR procedure tested | Quarterly drill; RTO ≤ 4h, RPO ≤ 24h | Foundation ✓ | `docs/runbooks/disaster-recovery.md` + drill log | Doc done |
| 24h soak passed | Memory stable, p99 within SLO, dropped frames < 0.1% | Phase 5 | `scripts/soak_simulate.py` output CSV | Pending |
| Camera rollout | 52-camera deployment confirmed stable for 7 days | Phase 6 | Deployment log | Pending |

---

## 5. Documentation Gates

| Gate | Criterion | Phase | Evidence | Status |
|---|---|---|---|---|
| CLAUDE.md current | All phase statuses accurate; no stale paths | Foundation ✓ | Review | Done |
| All plan statuses accurate | Every plan file shows correct COMPLETE/IN PROGRESS | Foundation ✓ | Review | Done |
| Onboarding runbook validated | External tester completes onboarding without assistance | Phase 4 | Tester sign-off | Pending |
| EXPLAINER.md links current | No broken internal links | Foundation | Link check | Pending |
| Production readiness spec | This document links from CLAUDE.md §1 | Foundation ✓ | CLAUDE.md | Done |

---

## 6. Capacity Claims

These numbers are targets validated by the Phase 5 soak test. Until soak passes, treat as estimates.

| Metric | Target | GPU SKU | Notes |
|---|---|---|---|
| Max concurrent cameras | 52 | NVIDIA A4000 16 GB | 1 InferenceEngine per 8-camera group |
| Frame throughput | 25 fps per camera | A4000 | SCRFD 2.5G + YOLOv8x-pose + BoT-SORT |
| Inference latency p99 | < 300 ms per frame | A4000 | End-to-end frame → TrackingEvent |
| FAISS search latency | < 5 ms for 100K embeddings | CPU | L2-normalized flat index |
| DB write throughput | 1,300 rows/s | PostgreSQL 16 + NVMe | tracking_events with pgvector |
| Memory (no GPU) | < 4 GB RSS | — | Ingestion + API + writer only |
| Memory (full pipeline) | < 12 GB RSS | A4000 | Includes FAISS + 52-cam ONNX sessions |

---

## 7. Per-Phase Gate-Closing Matrix

Phases 1A.1 through 2d are **COMPLETE** as of 2026-06-01 (405 tests passing). Phases 3–6 are pending.

| Gate category | 1A.1 ✓ | 1A.2 ✓ | 1B.1 ✓ | 1B.2 ✓ | 2a.1 ✓ | 2a.2 ✓ | Foundation ✓ | 2b ✓ | 2c ✓ | 2d ✓ | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SLOs (basic) | | | ✓ | | | | | | | | | | ✓ | |
| Security basics | | | ✓ | ✓ | | | | | | | | | ✓ | |
| GDPR basics | ✓ | ✓ | | ✓ | | | | | | | ✓ | | ✓ | |
| Operational docs | | | | | | | ✓ | | | | | | | |
| 24h soak | | | | | | | | | | | | | ✓ | |
| 52-cam rollout | | | | | | | | | | | | | | ✓ |

---

## 8. v1 GA Acceptance Criteria (All of the above, summarised)

A deployment is **GA-ready** when:

1. All COMPLETE phases above have passing test suites (current: **405 tests**, 5 deselected `heavy_models`)
2. Security review clean (Phase 5)
3. GDPR purge end-to-end proven in staging (Phase 1B.2 ✓)
4. Install runbook validated by external tester (Phase 4)
5. 24h soak passed at 52-camera load (Phase 5)
6. 7-day stable production deployment at first customer site (Phase 6)
