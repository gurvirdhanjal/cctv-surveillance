# VMS Customer Onboarding Runbook

**Target audience:** VMS installer / integrator
**Prerequisite:** Server is installed and healthy (`/api/health` returns `{"status":"ok"}`)
**Time:** ~4 hours for a typical 8-camera site

> **Phase 4 note:** This runbook is the specification for the onboarding wizard UI.
> The frontend wizard (Phase 4) implements these steps as guided screens.

---

## Step 1 — Server Install

Follow `docs/runbooks/install.md`.

**Verification:**
```bash
curl http://<server-ip>:8000/api/health
# Expected: {"status":"ok","db":"connected","redis":"connected"}
```

---

## Step 2 — Create First Admin User

```bash
docker compose exec vms-app python -m vms.cli users create \
    --admin \
    --email admin@customer.com \
    --password "SecurePass123!"
```

**Expected output:** `User created: admin@customer.com (role=admin)`

**Verification:**
```bash
curl -X POST http://<server>:8000/api/auth/token \
    -d '{"email":"admin@customer.com","password":"SecurePass123!"}' \
    -H "Content-Type: application/json"
# Expected: {"access_token":"...","token_type":"bearer"}
```

---

## Step 3 — Network Camera Discovery

1. Identify IP range of camera network (e.g., `192.168.10.0/24`).
2. Scan for RTSP streams:
   ```bash
   python -m vms.cli cameras discover --subnet 192.168.10.0/24
   ```
3. For each detected camera, note the RTSP URL (format: `rtsp://user:pass@ip:port/path`).
4. Add cameras to VMS:
   ```bash
   curl -X POST http://<server>:8000/api/cameras \
       -H "Authorization: Bearer $TOKEN" \
       -d '{"name":"Entrance-1","rtsp_url":"rtsp://admin:pass@192.168.10.5/stream1"}'
   ```

**Troubleshooting:**
- Camera not discovered: check VLAN routing; cameras and server must be on same L2 segment or have routing
- RTSP auth fails: verify credentials in camera firmware web UI

---

## Step 4 — Run CameraProfiler Per Camera

The profiler determines each camera's capability tier (FULL / MID / LOW).

```bash
python -m vms.cli profile --camera-id 1
```

**Expected output:**
```
Camera 1: Entrance-1
  Resolution: 1920x1080
  Frame rate: 25 fps
  Face area (median): 8,400 px² → FULL tier
  Profiling complete. Signed report: reports/camera_1_readiness.pdf
```

Repeat for all cameras. Cameras below LOW threshold (face area < 900 px²) cannot reliably identify persons; document in the site report.

---

## Step 5 — Calibrate Homography Per Camera

Homography maps camera pixel coordinates to floor-plan coordinates (metres).

1. Open the calibration UI at `http://<server>:8000/admin/cameras/<id>/calibrate`
2. Place 4 floor markers in the camera's field of view (corners of a known rectangle)
3. Click each marker in the camera preview; enter its floor-plan coordinates (x, y) in metres
4. Accept when reprojection error < 2 px

```bash
# Verify stored homography:
curl -H "Authorization: Bearer $TOKEN" \
     http://<server>:8000/api/cameras/1 | jq .homography_matrix
# Expected: non-null JSON string
```

**Troubleshooting:**
- Reprojection error > 2 px: use more precise marker placement; avoid fisheye lenses without undistortion

---

## Step 6 — Define Zones

Zones are polygons on the floor plan used for intrusion detection and zone-presence tracking.

1. Open the zone editor at `http://<server>:8000/admin/zones`
2. Draw polygon on the floor plan; name it (e.g., "Server Room", "Loading Dock")
3. Set adjacency links for cross-camera tracking (cameras whose fields of view overlap)
4. Assign maintenance windows (time ranges when intrusion alerts are suppressed)

```bash
# Verify zone created:
curl -H "Authorization: Bearer $TOKEN" http://<server>:8000/api/zones
```

---

## Step 7 — Configure RBAC

1. Create operator users:
   ```bash
   python -m vms.cli users create \
       --email operator1@customer.com \
       --role operator \
       --password "OperatorPass1!"
   ```
2. Assign camera and zone permissions:
   ```bash
   curl -X POST http://<server>:8000/api/users/<user_id>/permissions \
       -H "Authorization: Bearer $ADMIN_TOKEN" \
       -d '{"camera_ids":[1,2,3],"zone_ids":[1,2]}'
   ```
3. Verify the operator can only see their assigned cameras in the Guard view.

---

## Step 8 — Enrol First Persons

Each person should have at least 3 embeddings from different angles for reliable identification.

```bash
# Create person record
curl -X POST http://<server>:8000/api/persons \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"employee_id":"EMP001","name":"Alice Smith"}'

# Upload face images (repeat 3+ times from different angles)
curl -X POST http://<server>:8000/api/persons/1/embeddings \
    -H "Authorization: Bearer $TOKEN" \
    -F "image=@alice_front.jpg"

curl -X POST http://<server>:8000/api/persons/1/embeddings \
    -H "Authorization: Bearer $TOKEN" \
    -F "image=@alice_left.jpg"

curl -X POST http://<server>:8000/api/persons/1/embeddings \
    -H "Authorization: Bearer $TOKEN" \
    -F "image=@alice_right.jpg"
```

**Verification:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
     "http://<server>:8000/api/persons/search?q=Alice"
# Expected: person record with embedding_count >= 3
```

---

## Step 9 — Configure Alert Routing

Alerts can be dispatched via email (SMTP), Slack, Telegram, or webhook.

```bash
# SMTP example
curl -X POST http://<server>:8000/api/alert-routing \
    -H "Authorization: Bearer $TOKEN" \
    -d '{
      "alert_type": "INTRUSION",
      "channel": "smtp",
      "config": {
        "to": "security@customer.com",
        "subject_prefix": "[VMS ALERT]"
      }
    }'
```

**Test dispatch:**
```bash
curl -X POST http://<server>:8000/api/alert-routing/test \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"channel":"smtp"}'
# Expected: test email received within 30 seconds
```

---

## Step 10 — Run Acceptance Test

Walk an enrolled person and then an unknown person through Camera 1.

1. Have the enrolled person (from Step 8) walk past Camera 1's field of view.
2. Wait 10 seconds. Verify in Guard view:
   - A tracking event appears with the person's name
   - No `UNKNOWN_PERSON` alert fires

3. Have an unknown person (not enrolled) walk past Camera 1.
4. Wait 10 seconds. Verify:
   - An `UNKNOWN_PERSON` alert fires
   - Alert dispatched to configured email/Slack within 5 seconds

**Pass criteria:**
- [ ] Known person identified correctly ≥ 90% of frames
- [ ] Unknown person triggers alert within 15 seconds of entering zone
- [ ] Alert dispatched to correct channel
- [ ] No false positives during 30-minute idle period after walk

---

## Handoff Checklist

Before handing off to the customer:

- [ ] All cameras profiled and at least FULL or MID tier
- [ ] All homographies calibrated (reprojection error < 2 px)
- [ ] All zones defined and adjacency configured
- [ ] At least 3 operators created with correct camera/zone permissions
- [ ] At least 5 persons enrolled with ≥ 3 embeddings each
- [ ] Alert routing configured and tested
- [ ] Acceptance test passed for Camera 1
- [ ] Customer trained on Guard view and alert acknowledgment
- [ ] Backup configured and tested (see `backup-restore.md`)
- [ ] This runbook reviewed with customer IT contact
