# VMS Phase History

Completed phase records extracted from CLAUDE.md to keep §3 lean.
Reference here when you need delivery details for a completed phase.

---

## Phase 3 — Alert Dispatcher — COMPLETE

473 tests passing, 5 deselected. Plan: `docs/superpowers/plans/2026-06-06-vms-phase3-alert-dispatcher.md`.
Delivered: `vms/dispatcher/` package (payload.py, channels.py, router.py, worker.py), `AlertPayload` DTO + `from_stream_fields()`, `ChannelSender` Protocol, `WebhookSender` (HMAC-SHA256), `SlackSender`, `TelegramSender`, `EmailSender`, `match_routing_rules()` (NULL-wildcard semantics), `AlertDispatcher` with 3× exponential backoff (1s→4s→16s), dead-letter audit event, FastAPI lifespan integration, `GET/POST/DELETE /api/alert-routing` routes, 8 new config fields (smtp_*, slack_bot_token, telegram_bot_token, webhook_secret).

---

## PPE Compliance Detection — COMPLETE

405 tests passing, 5 deselected. Files: `vms/inference/ppe.py` (PPEModel — YOLOv8l SH17 ONNX, decodes (1,21,8400) output, NMS, returns `dict[str,float]` per crop), `vms/anomaly/detectors/ppe.py` (PPEDetector — alert_type=PPE_VIOLATION, HIGH, sustain_ms=3000, cooldown_ms=120000, gloves+mask opt-in via check_gloves/check_mask). `Tracklet` has 4 PPE fields (helmet, vest, gloves, mask conf, all float|None). `_score_ppe()` in InferenceEngine. SH17 class indices: helmet=10, vest=16, gloves=9, mask=5. Export model: `YOLO('models/sh17_ppe_yolov8l.pt').export(format='onnx',imgsz=640,opset=11,simplify=True)`. Activate: `VMS_PPE_MODEL=models/sh17_ppe_yolov8l.onnx`. CSRNet density detection deliberately deferred — wire when real deployment shows YOLO undercounting dense crowds.

---

## Phase 2d — Multi-Modal Person Tracking Upgrade — COMPLETE

372 tests passing, 5 deselected (`heavy_models`). Plan: `docs/superpowers/plans/2026-05-31-vms-v2-phase2d-multimodal-tracking-upgrade.md`. Delivered: `BodyEmbedder` (torchreid OSNet AIN x1.0 msmt17, 512-dim, Rank-1=73% on DukeMTMC), `FusionResolver` (Face ≻ Body ≻ BLE), `assign_and_identify()` returns 3-tuple `(gid, person_id, resolved_via)`, `db_writer` wires face+body embeddings + resolved_via, body Re-ID threshold `reid_body_confirmed_sim=0.51` (calibrated from simulation), `botsort_custom.yaml` (BoT-SORT + CMC), `Tracklet.keypoints`+`face_visible` fields, `PerCameraTracker` upgraded to YOLOv8x-pose + BoT-SORT, keypoint-gated SCRFD+AdaFace (ceiling cam GPU saving), `vms/ble/` BLE badge service (MQTT + zone resolver + Redis consumer), DB migration `942aa02e2872` (badge_id, ble_events, resolved_via), E2E Brijesh tracking test (entry gate → floor body Re-ID → BLE fallback). Both face AND body galleries now populate simultaneously so entry-gate identity follows person through ceiling cameras.

---

## Phase 2c — Cross-Camera Identity Hardening — COMPLETE

342 tests passing. Plan: `docs/superpowers/plans/2026-05-31-vms-v2-phase2c-cross-camera-identity-hardening.md`. Delivered: rolling gallery buffer (N=8 per tracklet), confirmed track promotion after N sightings (lower sim threshold + 10-min stale TTL), `CameraTopology` spatial-temporal gate (JSON-configurable per camera pair), `BodyEmbedder` (OSNet ONNX) as face-absent fallback with `Tracklet.body_embedding` field wired into `InferenceEngine`. Per-gid margin computation fix prevents false margin failures when same person has multiple camera tracklets. No schema migration required.

---

## Phase 2b — Anomaly Framework — COMPLETE

306 tests passing. Plan: `docs/superpowers/plans/2026-05-15-vms-v2-phase2b-anomaly-framework.md`. Delivered: `AnomalyDetector` ABC + `SeamProvider` Protocol, `DetectorRegistry`, `MaintenanceCalendar` (TTL cache + cron), `AlertFSM` (sustain/cooldown/dedup/maintenance suppression), 6 detectors (UNKNOWN_PERSON, PERSON_LOST, CROWD_DENSITY, INTRUSION, LOITERING, VIOLENCE), `ViolenceModel` ONNX wrapper, `DetectionFrame.violence_score`, `HeadCountAggregator`, `AnomalyOrchestrator` (error-isolated, seam-injected), inspection APIs, `vms-cli`, Prometheus metrics, structured logging, 2 E2E integration tests. Alembic migration `bc0e96331eb1` adds `alerts.dedup_key`, state/type CHECKs, seeds 6 detector rows.

---

## tracking_events Partitioning — COMPLETE

227 tests passing. Plan: `docs/superpowers/plans/2026-05-28-vms-tracking-events-partition.md`. Delivered: Alembic migration `e0183e05bf00` reconstructs `tracking_events` as `PARTITION BY RANGE (event_ts)` with composite PK `(event_id, event_ts)`; DEFAULT + current-month partitions; `vms/db/partition_manager.py` (`ensure_future_partitions`, `drop_partitions_before`, `list_partitions`); startup wired in `main.py`; `_ensure_partitions` autouse fixture in conftest; ORM composite PK updated; 8 new integration tests.

---

## Storage Abstraction Layer — COMPLETE

219 tests passing (176 pre-existing + 43 new). Plan: `docs/superpowers/plans/2026-05-28-vms-storage-abstraction.md`. Delivered: `StorageBackend` Protocol, `LocalStorageBackend`, `MinIOStorageBackend` (moto-tested), `get_storage()` factory, `write_thumbnail`/`write_snapshot` helpers, Alembic data migration for relative keys, GDPR purge wired to storage backend, `/media` StaticFiles mount for local backend. `boto3`/`moto[s3]` added to dependencies.

---

## Foundation Hardening & Docs Cleanup — COMPLETE

176 tests passing (commit `3bd6669`). Plan: `docs/superpowers/plans/2026-05-27-vms-foundation-hardening-and-docs-cleanup.md`. Delivered: production readiness spec, subphase taxonomy, configurable RTSP config, E2E integration test, four ops runbooks, customer onboarding runbook, Phase 3/5 scope stubs.

---

## Phase 1B.2 Hardening — COMPLETE

171 tests passing (commit `210b283`). Plan: `docs/superpowers/plans/2026-05-27-vms-v2-phase1b-2-hardening.md`. Fixes: GDPR purge (SELECT FOR UPDATE + file deletion + CLIP removal + JSON audit payload), SHM size validation, RTSP exponential backoff + camera deactivation, faiss_dirty consumer startup replay.

---

## Phase 1A.2 Hardening — COMPLETE

171 tests passing (commit `210b283`). Plan: `docs/superpowers/plans/2026-05-27-vms-v2-phase1a-2-hardening.md`. Fixes: datetime.utcnow column defaults, row_hash_version migration.

---

## Phase 2a.2 Hardening — COMPLETE

159 tests passing (commit `019e45e`). Plan: `docs/superpowers/plans/2026-05-14-vms-v2-phase2a-2-hardening.md`.

---

## Phase 2a.1 — Identity Framework — COMPLETE

128 tests passing (commit `634c8c4`). Plan: `docs/superpowers/plans/2026-05-14-vms-v2-phase2a-1-identity-framework.md`. Notes: `docs/superpowers/notes/2026-05-14-vms-v2-phase2a-implementation-notes.md`.

---

## Phase 1B.1 — Ingestion, Inference, and Base API — COMPLETE

96 tests passing (commit `019e45e`). Plan: `docs/superpowers/plans/2026-05-09-vms-v2-phase1b-1-ingestion-inference-api.md`. Notes: `docs/superpowers/notes/2026-05-09-vms-v2-phase1b-implementation-notes.md`.

---

## Phase 1A.1 — Database Schema, Project Scaffold, and Config — COMPLETE

57 tests passing (commit `4a4bc49`). Plan: `docs/superpowers/plans/2026-05-01-vms-v2-phase1a-1-db-schema.md`.
