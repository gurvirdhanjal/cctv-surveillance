# VMS Upgrade Runbook

**Pre-requisite:** Take a backup first. See `backup-restore.md`.

---

## 1. Pre-Upgrade Checklist

- [ ] Backup database: `pg_dump vms > vms_backup_$(date +%Y%m%d).sql`
- [ ] Note current version: `docker compose exec vms-app python -m vms.cli version`
- [ ] Read the release notes for breaking changes
- [ ] Schedule a maintenance window (typically 15 minutes)
- [ ] Notify operators

---

## 2. Alembic Migration Order

Always upgrade head, never skip versions:
```bash
alembic upgrade head
```

To check pending migrations:
```bash
alembic current
alembic history --verbose
```

---

## 3. Zero-Downtime Rollout (Blue/Green via nginx)

1. Pull new image: `docker pull vms-app:NEW_VERSION`
2. Start green container on port 8001: `docker run -d -p 8001:8000 vms-app:NEW_VERSION`
3. Apply migrations: `docker exec green-container alembic upgrade head`
4. Health-check green: `curl http://localhost:8001/api/health`
5. Swap nginx upstream from port 8000 to 8001
6. Wait for in-flight requests to drain (30s)
7. Stop blue container
8. Run smoke test (see §6)

---

## 4. Model Manifest Update

```bash
python -m vms.cli models list          # see current versions
python -m vms.cli models download      # fetch new versions from manifest
python -m vms.cli models verify        # verify checksums
# To pin a specific model version:
python -m vms.cli models pin scrfd 2.5g-v2
```

---

## 5. Rollback Procedure

If upgrade fails after migration:
1. Stop new container
2. Apply downgrade: `alembic downgrade -1`
3. Restart previous container version
4. Verify health endpoint

> **Warning:** Only downgrade one revision at a time. Read each migration's `downgrade()` before executing.

---

## 6. Post-Upgrade Smoke Test

```bash
# Health check
curl http://localhost:8000/api/health

# Test person search
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/api/persons/search?q=test

# Confirm tracking events still flowing
psql $VMS_DB_URL -c "SELECT COUNT(*) FROM tracking_events WHERE ingest_ts > NOW() - INTERVAL '1 minute';"
```
