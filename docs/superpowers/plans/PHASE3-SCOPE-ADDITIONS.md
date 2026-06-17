# Phase 3 — Additional scope captured 2026-05-27

## SYSTEM_HEALTH alert channel (from /plan-eng-review D2)

- New alert_type values: `CAMERA_DOWN`, `FAISS_STALE`, `SCHEDULER_STALLED`,
  `DISK_HIGH`, `INFERENCE_LAG_HIGH`
- Two new detector classes: `CameraHealthDetector`, `ServiceHealthDetector`
- Reuses existing `AlertDispatcher`; new alert_routing rules target ops role
  instead of security role
- Operators see system alerts in a separate dashboard tab (Phase 4)

## Reason

Anomaly framework alerts only on people-events. Silent system failures (camera
drops, FAISS staleness, scheduler stalls) currently produce no alerts.
See decision log D2 in `2026-05-27-vms-foundation-hardening-and-docs-cleanup.md`.
