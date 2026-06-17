# VMS Backup and Restore Runbook

---

## 1. What to Back Up

| Item | Location | Frequency | Tool |
|---|---|---|---|
| PostgreSQL database | `$VMS_DB_URL` | Nightly | `pg_dump` |
| Face thumbnails | `VMS_THUMBNAIL_DIR` | Nightly | `rsync` |
| Model manifest lockfile | `models/manifest.lock` | On change | `cp` |
| Configuration / secrets | `/etc/vms/env` or `.env` | On change | Encrypted copy |
| FAISS index | (not needed) | — | Rebuilt from DB on startup |

---

## 2. Backup Procedure

### Database
```bash
pg_dump -Fc -h localhost -U vms vms > /backups/vms_$(date +%Y%m%d_%H%M%S).dump
# Verify: check file size > 0
ls -lh /backups/vms_*.dump | tail -5
```

### Face thumbnails
```bash
rsync -avz --checksum $VMS_THUMBNAIL_DIR /backups/thumbnails/
```

### Automated nightly (cron example)
```cron
0 2 * * * /opt/vms/scripts/backup.sh >> /var/log/vms-backup.log 2>&1
```

---

## 3. Restore Procedure

1. Stop all VMS services:
   ```bash
   docker compose down
   # or: sudo systemctl stop vms-app vms-worker
   ```

2. Restore database:
   ```bash
   createdb -h localhost -U vms vms_restore
   pg_restore -Fc -h localhost -U vms -d vms_restore /backups/vms_20260101_020000.dump
   # Swap to restored DB: update VMS_DB_URL to point to vms_restore
   ```

3. Restore thumbnails:
   ```bash
   rsync -avz /backups/thumbnails/ $VMS_THUMBNAIL_DIR
   ```

4. Restart services:
   ```bash
   docker compose up -d
   ```

5. FAISS rebuilds automatically on startup from `person_embeddings` table.

---

## 4. Restore Validation

```bash
# 1. Health check
curl http://localhost:8000/api/health

# 2. Verify last 5 audit events have valid hash chain
psql $VMS_DB_URL -c "
SELECT event_id, event_type, row_hash_version,
       LEFT(row_hash, 8) AS hash_prefix
FROM audit_log
ORDER BY event_id DESC
LIMIT 5;"

# 3. Test one search query to confirm FAISS is working
curl -H "Authorization: Bearer $TOKEN" \
     "http://localhost:8000/api/persons/search?q=test_person"
```

---

## 5. Backup Schedule Recommendation

| Backup type | Frequency | Retention |
|---|---|---|
| Database full dump | Nightly at 02:00 | 30 days on-site, 90 days offsite |
| Thumbnail incremental | Nightly at 03:00 | 90 days |
| Weekly full filesystem | Weekly Sunday 04:00 | 12 weeks |
