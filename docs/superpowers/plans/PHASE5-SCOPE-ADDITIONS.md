# Phase 5 — Additional scope captured 2026-05-27

## Configurable per-table data retention (from /plan-eng-review D3)

- `tracking_events`: default 90 days, monthly partitioning, drop oldest partition
- `alerts`: default 1 year
- `person_clip_embeddings`: default 30 days (matches forensic search window)
- `audit_log`: default 7 years (legal retention)
- All retention values configurable via `Settings`; per-customer override possible
- Nightly prune job in `vms.scheduler`

## 24h soak / load test (from /plan-eng-review D10)

- `scripts/soak_simulate.py` replays pre-recorded video files as 52 virtual cameras
- Output: CSV of memory + latency + dropped-frame metrics over 24h
- Validates v2 spec §K capacity claims before any sales conversation
- Acceptance criteria: stable memory (no growth > 5% over 24h), p99 latency
  within spec, dropped-frame rate < 0.1%

## Reason

See decision log D3 + D10 in `2026-05-27-vms-foundation-hardening-and-docs-cleanup.md`.
