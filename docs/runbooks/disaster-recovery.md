# VMS Disaster Recovery Runbook

**RTO target:** 4 hours
**RPO target:** 24 hours
**Last tested:** (fill in date after first DR drill)

---

## 1. Incident Classification

| Scenario | Severity | Expected RTO |
|---|---|---|
| Server power failure (hardware OK) | P2 | 30 min |
| GPU failure | P2 | 2 hours (degraded mode) |
| Storage failure (OS disk) | P1 | 4 hours |
| Full site loss (fire/flood) | P0 | 24 hours |
| Network partition | P2 | 15 min |

---

## 2. Server-Down Procedure (Hardware OK)

1. Power cycle or restart server
2. Services auto-start via systemd/Docker Compose restart policies
3. Verify: `curl http://localhost:8000/api/health`
4. FAISS index rebuilds automatically (~60s for 10K embeddings)
5. If DB fails to start: check disk space (`df -h`) and PG logs

---

## 3. Cold-Spare Hardware Swap (Storage Failure)

1. Mount latest backup media on spare server
2. Install VMS on spare server (see `install.md`)
3. Restore database from backup:
   ```bash
   pg_restore -Fc -h localhost -U vms -d vms /backups/latest.dump
   ```
4. Restore thumbnails directory
5. Update DNS/IP routing to point to spare server
6. Verify health endpoint

---

## 4. GPU Failure — Degraded Mode

When the GPU fails, inference is unavailable. The system continues:
- Camera ingestion (frame capture to SHM + Redis) continues
- DB writer continues (tracking events write with null person_id)
- API continues (health, person search return stale data)

To enable CPU-only inference (slower, <=4 cameras):
```bash
export VMS_ONNX_PROVIDER=CPUExecutionProvider
sudo systemctl restart vms-worker
```

Replace GPU when available; restart workers to restore full inference.

---

## 5. Network Partition

If the server loses connectivity to cameras:
- IngestionWorker applies exponential backoff (config: `VMS_RTSP_FAILURE_THRESHOLD`)
- Camera marked `is_active=False` after threshold failures
- Alert dispatch falls back to local SMTP relay if configured

To manually reactivate cameras after network is restored:
```bash
psql $VMS_DB_URL -c "UPDATE cameras SET is_active=TRUE WHERE is_active=FALSE;"
sudo systemctl restart vms-worker
```

---

## 6. Full Site Loss

1. Retrieve offsite backup (encrypted, verify checksum first)
2. Provision new server at DR site
3. Follow `install.md`
4. Restore from offsite backup (see `backup-restore.md §3`)
5. Update camera RTSP URLs if cameras are at a different location
6. Reactivate cameras: `UPDATE cameras SET is_active=TRUE;`
7. Notify operators of partial data loss (RPO = time since last backup)

---

## 7. DR Drill Checklist (Run Quarterly)

- [ ] Restore database to test server from latest nightly backup
- [ ] Verify audit log hash chain integrity (5 most recent events)
- [ ] Verify person search returns expected results
- [ ] Verify FAISS rebuilds within 5 minutes
- [ ] Verify camera ingestion restarts after simulated failure
- [ ] Update "Last tested" date at top of this document
