# VMS App Flow

_User journeys for each role. Tech stack and component details: `docs/superpowers/specs/2026-05-01-vms-frontend-design.md`._

---

## Roles

| Role | Primary goal | Landing page |
|---|---|---|
| **Guard** | React to live alerts; track persons in real time | `/live` |
| **Manager** | Investigate incidents; review analytics | `/analytics` |
| **Admin** | Configure the system; enroll persons; manage cameras | `/admin` |

All roles share: `/login`, `/settings/profile`, `/forensic` (read-only for guard).

---

## Guard flow

Guards work from a single always-on screen (dark theme, 1920×1080+).

### 1. Login
```
/login → enter username + password → JWT issued (8h) → redirect /live
```

### 2. Live view (`/live`)

```
┌─────────────────────────────────────────────────────────────┐
│ TopBar: site name · head count · GPU % · active alert count │
├──────────────┬──────────────────────────────┬───────────────┤
│ CameraGrid   │ Focused camera (HLS stream)  │ AlertSidebar  │
│ 4×3 tiles    │ + bounding-box overlays      │ newest first  │
│ 2s snapshots │ + name labels                │               │
└──────────────┴──────────────────────────────┴───────────────┘
```

- **Tile click** → swaps that camera into the focused position
- **Head count badge** → click shows per-zone breakdown modal
- **Alert card** → shows type, severity, camera, timestamp; actions: Acknowledge / Resolve

### 3. Alert received

```
AlertFSM fires event
  → WebSocket pushes alert_fired to browser (≤250ms target)
    → AlertSidebar prepends card (CRITICAL = red banner + sound)
      → Guard reads: alert type, zone, camera name, thumbnail
```

Alert lifecycle:
```
active → [Guard clicks Acknowledge] → acknowledged
acknowledged → [Guard clicks Resolve] → resolved
active → [maintenance window covers it] → suppressed
```

### 4. Follow a person

```
Guard spots suspicious track →
  clicks name label on focused camera →
    navigates /live/follow/:trackId →
      FollowPersonPanel shows:
        - current camera + bbox
        - last 5 camera transitions
        - zone dwell times (last 30 min)
        - "who is this?" → person profile if known
```

### 5. Focused camera

```
/live/cameras/:cameraId
  → full-screen HLS stream
  → all active tracklets overlaid (bbox + name/UNKNOWN label)
  → keyboard Esc → back to /live
```

---

## Manager flow

Managers use a light-theme interface, typically in an office after an incident or at shift review.

### 1. Analytics dashboard (`/analytics`)

Default view after login for manager role.

```
/analytics
  ├── daily totals: persons detected, unknown count, alerts fired, camera uptime
  ├── zone heatmap (last 24h traffic density)
  └── top 5 alerts by type (bar chart)
```

### 2. Investigate an incident — timeline playback

```
Manager sees a report of an incident →
  /analytics/timeline →
    set time window (from / to) →
      timeline renders all tracking_events for that window on floor plan
        → scrub forward/backward
        → click a dot → person card (name, employee_id, or UNKNOWN)
```

### 3. Person profile

```
/analytics/persons/:id
  ├── 24h movement trail on floor plan
  ├── zone dwell-time bar chart (per zone)
  ├── alert history for this person
  └── last known camera + timestamp
```

### 4. Heatmap view

```
/analytics/heatmap
  → floor plan image
  → colour overlay: hot = high dwell time, cool = low traffic
  → filter by zone, time range
  → export CSV (zone presence data)
```

### 5. Forensic search

```
/forensic
  → text description search ("person in red helmet near gate 3")
  → results: ranked clip thumbnails with timestamp + camera
  → click clip → video snippet + person card (if identified)
```

> Forensic search requires CLIP embedding pipeline — deferred to Phase 5.

---

## Admin flow

Admins configure the system and manage users/persons. They can also access all Guard and Manager views.

### 1. System health (`/admin`)

```
/admin
  ├── worker status tiles (Ingestion, Inference, Identity, DBWriter — green/red)
  ├── GPU utilisation graph (last 1h)
  ├── Redis stream lag per camera group
  ├── PostgreSQL write queue depth
  └── recent SYSTEM_CRITICAL alerts
```

### 2. Enroll a person

```
/admin/persons
  → "New Person" button
    → EnrolmentWizard:
        Step 1: name, employee_id, department, person_type
        Step 2: capture/upload ≥6 face images
                (quality check per image — blur score must pass)
        Step 3: confirm → POST /api/persons + POST /api/persons/{id}/embeddings
                → FAISS rebuild triggered (≤5s)
        → person appears in search
```

### 3. Add / configure a camera

```
/admin/cameras
  → "Add Camera" → name + RTSP URL + worker_group
  → "Profile" button → triggers camera profiler
      → sets capability_tier (FULL/MID/LOW) based on FPS, resolution, latency
  → "Calibrate" button → HomographyCalibrator:
      → capture frame
      → mark 4 reference points on frame
      → match to floor plan coordinates
      → if reprojection error ≥2px → rejected with message
      → success → homography_matrix saved
```

### 4. Define zones

```
/admin/zones
  → ZoneEditor on floor plan image
  → draw polygon → set name, max_capacity, loiter_threshold_s, is_restricted
  → save → zone appears in analytics + alert routing
```

### 5. Configure anomaly detectors

```
/admin/anomaly-detectors
  → list of 7 detectors with enabled/disabled toggle
  → click detector → expand config panel
      → per-detector JSON config (sustain_ms, cooldown_ms, thresholds)
      → PATCH /api/anomaly-detectors/{id}
```

### 6. Set up alert routing

```
/admin/alert-routing
  → table of routing rules
  → "Add Rule" → alert_type (or ALL), severity (or ALL), zone (or ALL), channel, target
  → channels: Email, Slack, Telegram, Webhook, WebSocket
  → test dispatch button (sends a sample alert to that channel)
```

### 7. Schedule maintenance windows

```
/admin/maintenance
  → MaintenanceCalendar (month view)
  → click time slot → "New Window":
      scope: CAMERA or ZONE → pick scope_id
      type: ONE_TIME → pick start + end
            RECURRING → cron expression + duration_minutes
      suppress_alert_types: specific types or ALL
  → active windows show as greyed camera tiles in Guard view
```

### 8. Manage users

```
/admin/users
  → list users with role badges
  → "Add User" → username, role, camera permissions
  → edit role / deactivate / reset password
```

### 9. GDPR person purge

```
/admin/persons → find person → "Purge"
  → confirmation modal: type full name + reason
  → POST /api/persons/{id}/purge (admin only)
  → embeddings blanked, thumbnail deleted, audit event written
  → person_id in tracking_events SET NULL (history preserved anonymously)
```

### 10. Audit log

```
/admin/audit
  → searchable table: event_type, actor, target, timestamp
  → "Verify chain" → GET /api/audit/verify → pass/fail hash check
  → "Export" → download signed PDF (Phase 5)
```

---

## Navigation rules

| From | Can reach | Cannot reach |
|---|---|---|
| Guard | `/live/*`, `/forensic` (read-only), `/settings/profile` | `/analytics/*`, `/admin/*` |
| Manager | All Guard routes + `/analytics/*`, `/forensic` | `/admin/*` |
| Admin | All routes | — |

Route guards enforced both client-side (React Router + `RoleGuard`) and server-side (JWT role check on every API call).

---

## Real-time events (WebSocket)

| Event | Who sees it | Triggered by |
|---|---|---|
| `alert_fired` | Guard (AlertSidebar) | AlertFSM |
| `person_location` | Guard (floor-plan dots) | InferenceEngine, throttled 5fps |
| `camera_snapshot` | Guard (CameraGrid tiles) | Ingestion, every 2s |
| `track_corrected` | Guard (label update) | Admin identity correction |

WebSocket reconnects transparently; on reconnect the client calls `GET /api/state/snapshot` to rehydrate before processing diffs.
