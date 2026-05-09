# VMS v2 — Frontend Design Specification

**Design Specification** · 2026-05-01
**Status:** Approved · Companion to `2026-05-01-vms-v2-hardened-design.md` §12 (high-level frontend)
**Audience:** Frontend engineers implementing the React app in Phase 4.

This document is the source of truth for the frontend. Every component, screen, and interaction below should be implementable without further design discussion.

---

## §1. Overview

The frontend serves three audiences with distinct mental models:

| User | Primary task | Frequency | Environment |
|---|---|---|---|
| **Guard** | Watch live feeds + respond to alerts | All-day, single window | Dark control-room display, often a 24"+ monitor |
| **Manager** | Review analytics, investigate after-the-fact | Daily / weekly | Office desktop, sometimes laptop |
| **Admin** | Configure cameras, zones, users, models, schedules | Setup + occasional adjustment | Desktop |

The app is **one Single-Page Application** with role-gated routes. Same codebase, same deployment, different views surfaced by JWT role.

### Goals

- Live alert latency from server-emit to on-screen ≤ 250ms.
- Floor-plan dot updates throttled to 5fps, smooth.
- 4 simultaneous HLS video streams without dropping frames on the Guard screen.
- Recover from WebSocket disconnect transparently — operator should not see broken state.
- Accessible to operators with screen readers (WCAG 2.1 AA target).
- Bundle ≤ 800kB gzipped initial JS; < 300kB on subsequent route changes.

### Non-goals (v1)

- Mobile-first responsive design — laptop/desktop only. Mobile companion app is v2.x.
- Multi-language UI on day-1 — i18n hook in place; English only for v1, Hindi added in v2.x.
- Offline mode beyond WebSocket reconnect — if the API is down, the app shows degraded banner; no caching of historical data for offline browsing.

---

## §2. Tech stack (consolidated from v1 §12)

| Layer | Choice | Why |
|---|---|---|
| Framework | React 18 + TypeScript 5.4 | Industry standard, strong type safety, large hiring pool |
| Build tool | Vite 5 | Fast HMR, ESM-native, simple config |
| Styling | Tailwind CSS 3.4 + shadcn/ui | Tailwind for speed, shadcn for accessible primitives. Avoid heavyweight UI libs |
| Server state | TanStack Query 5 (React Query) | Caching, background refetch, optimistic updates |
| Client state | Zustand 4 | Tiny (~1kB), no provider tree, sufficient for our needs |
| Real-time | socket.io-client 4 | Auto-reconnect, namespace support, drop-in pair with FastAPI Socket.io |
| Routing | React Router 6.22 | Standard; supports loaders + actions |
| Forms | React Hook Form 7 + Zod 3.23 | Performance + type-safe validation |
| Maps / floor plan | Leaflet 1.9 + react-leaflet 4 | Image overlay + polygon draw + custom marker layer for live person dots |
| Charts | Recharts 2.12 | Sufficient for line/bar/area; no need for D3 directly |
| Video | HLS.js 1.5 | HLS playback with clean buffer management |
| Date | date-fns 3 + date-fns-tz 3 | Tree-shakeable; explicit tz handling |
| Auth | JWT in httpOnly cookie + Authorization header for fetch | Standard pattern; CSRF mitigated by SameSite=Strict |
| Testing | Vitest 1.6 + React Testing Library 16 + Playwright 1.44 | Unit + integration via RTL; E2E via Playwright headless |
| Linting | ESLint 9 + typescript-eslint 7 + prettier 3 | Standard |

---

## §3. Information architecture & routing

```
/                          → redirect to /live (guard, manager) or /admin (admin)
/login                     → login form (public)
/live                      → Guard view
/live/cameras/:cameraId    → focused camera stream
/live/follow/:trackId      → "follow person" mode
/analytics                 → Management view (default analytics page)
/analytics/timeline        → time-scrubber playback
/analytics/heatmap         → floor-plan heatmap
/analytics/persons/:id     → person profile (24h journey, dwell)
/forensic                  → forensic CLIP search
/admin                     → admin dashboard (system health)
/admin/persons             → enrolment list + wizard
/admin/cameras             → camera config + profiler trigger
/admin/zones               → zone editor (polygon draw on floor plan)
/admin/users               → user management
/admin/maintenance         → maintenance windows calendar
/admin/anomaly-detectors   → enable/disable + per-detector config
/admin/alert-routing       → routing rule CRUD
/admin/models              → installed models + per-camera overrides
/admin/audit               → audit log search + verify
/settings/profile          → current-user profile, change password
/403                       → forbidden
/404                       → not found
```

### Role guards

| Role | Allowed routes |
|---|---|
| `guard` | `/live/*`, `/forensic` (read-only), `/settings/profile` |
| `manager` | guard routes + `/analytics/*`, `/forensic`, `/settings/profile` |
| `admin` | all routes |

Implemented via a `<RoleGuard allowed={[…]}>` wrapper on every protected route. JWT role decoded client-side for routing decisions; server still authorises every API call independently.

---

## §4. File layout

Feature-based, not type-based. Each feature owns its components, hooks, types, and tests:

```
frontend/
├── src/
│   ├── main.tsx
│   ├── app/
│   │   ├── App.tsx                  # router + theme + query client root
│   │   ├── routes.tsx               # route table with lazy loaders
│   │   └── providers.tsx            # composition of all providers
│   ├── shared/
│   │   ├── api/
│   │   │   ├── client.ts            # fetch wrapper, JWT injection, error mapping
│   │   │   ├── socket.ts            # socket.io client + reconnect
│   │   │   └── types.ts             # generated from OpenAPI (Phase 4 task)
│   │   ├── auth/
│   │   │   ├── AuthProvider.tsx
│   │   │   ├── useAuth.ts
│   │   │   └── RoleGuard.tsx
│   │   ├── design-system/
│   │   │   ├── tokens.ts            # color/spacing/typography constants
│   │   │   ├── ThemeProvider.tsx
│   │   │   └── components/          # shadcn-derived primitives (Button, Input, Modal, etc.)
│   │   ├── hooks/                   # cross-feature hooks: useDebounce, useInterval, etc.
│   │   ├── i18n/                    # react-intl config + en messages
│   │   └── utils/
│   ├── features/
│   │   ├── live/                    # guard view
│   │   │   ├── pages/
│   │   │   │   ├── LivePage.tsx
│   │   │   │   ├── FocusedCameraPage.tsx
│   │   │   │   └── FollowPersonPage.tsx
│   │   │   ├── components/
│   │   │   │   ├── CameraGrid.tsx
│   │   │   │   ├── CameraTile.tsx
│   │   │   │   ├── AlertSidebar.tsx
│   │   │   │   ├── AlertCard.tsx
│   │   │   │   ├── SystemStatusStrip.tsx
│   │   │   │   ├── HeadCountBanner.tsx
│   │   │   │   └── FollowPersonPanel.tsx
│   │   │   ├── hooks/
│   │   │   │   ├── useLiveAlerts.ts
│   │   │   │   ├── useCameraSnapshot.ts
│   │   │   │   └── useTrackedPersons.ts
│   │   │   ├── store/
│   │   │   │   └── liveStore.ts     # zustand slice
│   │   │   └── types.ts
│   │   ├── analytics/
│   │   │   ├── pages/
│   │   │   ├── components/
│   │   │   │   ├── FloorPlan.tsx
│   │   │   │   ├── TimeScrubber.tsx
│   │   │   │   ├── HeatmapOverlay.tsx
│   │   │   │   ├── DwellChart.tsx
│   │   │   │   └── PersonTimeline.tsx
│   │   │   └── hooks/
│   │   ├── forensic/
│   │   │   ├── pages/ForensicSearchPage.tsx
│   │   │   └── components/ClipResultCard.tsx
│   │   └── admin/
│   │       ├── pages/
│   │       ├── components/
│   │       │   ├── EnrolmentWizard.tsx
│   │       │   ├── HomographyCalibrator.tsx
│   │       │   ├── ZoneEditor.tsx
│   │       │   ├── MaintenanceCalendar.tsx
│   │       │   ├── ModelManager.tsx
│   │       │   ├── PerCameraOverrides.tsx
│   │       │   └── AuditLogViewer.tsx
│   │       └── hooks/
│   └── test-utils/
├── public/
├── index.html
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── package.json
└── playwright.config.ts
```

The frontend lives in a `frontend/` subdirectory of the repo root, separate from the Python `vms/` package. Built artefacts are served by the FastAPI server in production via static-file mount.

---

## §5. Design tokens

### Colour palette

Two themes — **dark** (default for Guard view, control rooms) and **light** (Admin, Analytics).

```ts
// src/shared/design-system/tokens.ts
export const colors = {
  // brand
  brand: {
    50:  '#eef6ff',
    100: '#d9eaff',
    300: '#7eb0ff',
    500: '#2b6cb0',  // primary brand
    700: '#1a4480',
    900: '#102a4c',
  },
  // alert severity (universal — same in both themes)
  severity: {
    critical: '#dc2626',  // red-600
    high:     '#ea580c',  // orange-600
    medium:   '#d97706',  // amber-600
    low:      '#65a30d',  // lime-600
  },
  // semantic tokens — resolved per theme
  text: {
    primary:   { dark: '#f3f4f6', light: '#0f172a' },
    secondary: { dark: '#9ca3af', light: '#475569' },
    muted:     { dark: '#6b7280', light: '#94a3b8' },
  },
  surface: {
    base:  { dark: '#0a0e1a', light: '#ffffff' },
    raised: { dark: '#111827', light: '#f8fafc' },
    sunken: { dark: '#020617', light: '#f1f5f9' },
  },
  border: {
    default: { dark: '#1f2937', light: '#e2e8f0' },
    strong:  { dark: '#374151', light: '#cbd5e1' },
  },
};
```

Tailwind config imports these into a custom palette so utilities like `bg-surface-base text-text-primary` work in both themes via CSS custom properties.

### Typography

```
Display:  Inter Display 700/600 — 32 / 28 / 24
Body:     Inter 400/500/600     — 16 / 14 / 13
Mono:     JetBrains Mono 400/500 — 13 / 12 (used for IDs, timestamps)
```

Self-hosted via `@fontsource/inter` and `@fontsource/jetbrains-mono` — no Google Fonts CDN (privacy + offline operation).

### Spacing scale

Tailwind default 4-unit scale (4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128). Don't use ad-hoc pixel values.

### Elevation

```
shadow-1: 0 1px 2px rgba(0,0,0,0.06)        — cards
shadow-2: 0 4px 6px rgba(0,0,0,0.10)        — popovers
shadow-3: 0 10px 25px rgba(0,0,0,0.20)      — modals
```

Dark theme uses lower opacity (0.40 multiplier) since shadow contrast is reversed.

### Motion

```
duration-fast:   120ms   — hover, focus rings
duration-base:   200ms   — page transitions, drawer open
duration-slow:   400ms   — large layout shifts
easing-standard: cubic-bezier(0.4, 0, 0.2, 1)
easing-emphasized: cubic-bezier(0.2, 0, 0, 1)
```

Respect `prefers-reduced-motion` — when set, durations collapse to 0 except for opacity.

---

## §6. Guard view (`/live`) — detailed layout

Default landing page for guards. Always-on, three-column layout optimised for a 1920×1080+ display.

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ ┌────────────────────────────────────────────────────────────────────────────────────┐   │  ← TopBar (h-14)
│ │ [Logo]  Plant Floor — Live    [Cmd+K Search]    [HeadCount: 23]  [GPU 78%] [Alerts 4] │
│ └────────────────────────────────────────────────────────────────────────────────────┘   │
├────────────────────────┬───────────────────────────────────────────────┬─────────────────┤
│                        │                                               │                 │
│   CameraGrid           │           Focused Camera (HLS)                │   AlertSidebar  │
│   (4×3 = 12 tiles      │           ────────────────────                │   ────────────  │
│    with paginator)     │           ▶ Loading Bay 2 (1080p)             │   [CRITICAL]    │
│                        │           [view tracklets overlay]            │   Violence     │
│   [Tile 1] [Tile 2]    │           [bbox + name labels]                │   2m ago       │
│   [Tile 3] [Tile 4]    │                                               │   Loading Bay  │
│   [Tile 5] [Tile 6]    │                                               │   ────         │
│   [Tile 7] [Tile 8]    │                                               │   [HIGH]       │
│   ...                  │                                               │   Unknown      │
│                        │                                               │   Person       │
│                        │                                               │   ────         │
│                        │                                               │   [ack][resolve]│
│                        │                                               │                 │
└────────────────────────┴───────────────────────────────────────────────┴─────────────────┘
```

Width allocations: CameraGrid 320px, Focused 1fr, AlertSidebar 380px.

### `<TopBar />`

- **Logo** — link to `/live`
- **Title** — current site name from `Settings`
- **Search (Cmd+K)** — global person search (autocomplete from `/api/persons/search`); selecting a person navigates to `/live/follow/:trackId` if currently tracked, else to `/analytics/persons/:id`
- **HeadCount badge** — live total persons in plant; click → modal with per-zone breakdown
- **GPU utilisation bar** — single bar 0–100%, colour-graded; click → admin if user is admin, otherwise read-only popover
- **Active alerts count** — link to AlertSidebar (autoscroll to top)

### `<CameraGrid />`

- 4×3 tile grid; tiles refresh JPEG snapshots every 2s via `GET /api/cameras/:id/snapshot`
- Active tile (the one displayed in Focused) is highlighted with a 2px brand border + persistent label
- Paginator: keyboard arrows (←/→) cycle pages; Esc returns to focused tile
- Tile shows: camera name, capability tier badge (FULL/MID/LOW), status icon (online/offline/maintenance)
- Maintenance-window cameras show a calendar icon + dimmed state — clicking shows the window detail
- Click → swap into focused position (HLS stream auto-attached)

### `<CameraTile />`

```tsx
type CameraTileProps = {
  camera: { id: number; name: string; tier: 'FULL'|'MID'|'LOW'; status: CameraStatus };
  isFocused: boolean;
  onSelect: () => void;
};
```

States: `online`, `offline`, `auth_failed`, `maintenance`. Each rendered with a distinct status icon + badge. `auth_failed` shows a warning amber border.

### `<FocusedCamera />`

- HLS playback via HLS.js attached to a single `<video>` element
- Bounding-box overlay on top of the video — SVG layer subscribed to `person_location` WebSocket events for the focused camera, throttled at 5fps
- Persons with `person_id` show name + colour band; unknown persons show a red dotted box
- "Follow" CTA on each detected person — clicking adds them to follow mode
- Bottom strip: timeline of the last 60s of detection events (sparkline of person count)

### `<AlertSidebar />`

- Sorted by severity DESC, then triggered_at DESC
- Grouped by `global_track_id` — multiple alerts for the same person collapse into "+ N similar"
- Each card: severity colour bar, type, time since, camera + zone, two CTAs (Acknowledge, Resolve)
- Auto-scroll behaviour: stays at top unless operator scrolled down (then sticky); toast "New alerts above ↑" appears
- Clicking an alert auto-focuses its camera in `<FocusedCamera />`
- Filter dropdown: by severity, type, zone

### `<HeadCountBanner />` (top of sidebar OR collapsed in TopBar)

```
┌──────────────────────────────────────────────────┐
│  Plant total: 23                              ▼  │
│  ─────────────────────────────────────────────   │
│  Loading Bay     5  ▼  ▼  ▼  ▼  ▼               │
│  Welding Bay     0                              │
│  Office          12  ▼  ▼  ▼  ▼  ▼  ▼  ▼  ▼ ... │
│  Cafeteria       6   ▼  ▼  ▼  ▼  ▼  ▼            │
└──────────────────────────────────────────────────┘
```

Tiny dots indicate count visually. Updates from WebSocket `head_count` event (new event added in §10 of this spec).

### `<FollowPersonPanel />` (`/live/follow/:trackId`)

Replaces FocusedCamera + parts of CameraGrid:

- Auto-switches the focused video to whichever camera currently has the tracklet
- Shows movement timeline strip across the top — colour-coded segments per camera
- Mini floor-plan in bottom-right showing live position of the tracked person
- Consistent colour/label across all overlays for the followed track

---

## §7. Management view (`/analytics`)

Light theme by default. Multi-page; each page focused on one analytical task.

### `/analytics` — Dashboard

Three rows:

1. **KPIs** — 4 metric cards: today's head count peak, average dwell, unknown person events, camera uptime %
2. **Charts** — line chart of head count over last 7 days, bar chart of alert volume by type (top 5)
3. **Quick actions** — "Open timeline scrubber", "View floor heatmap", "Search forensic clips"

### `/analytics/timeline` — Time scrubber playback

```
┌──────────────────────────────────────────────────────────────────────┐
│  Floor Plan with live person dots                                    │
│                                                                       │
│   ●  ●           ●                                                    │
│        ●             ●  ●                                             │
│                                ●                                      │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
[2026-04-30  ◀───────────────●───────────────▶  2026-05-01]
                              09:42:15
[ ⏸ play | ▶ ◀◀ ◀ ▶ ▶▶ | speed: 1× ▼ | filter: zone... | persons... ]
```

- Date/time slider (24h window default; configurable up to 7 days)
- Floor plan reconstructs person trails from `tracking_events` for the selected window
- Playback speeds: 0.5×, 1×, 2×, 5×, 10× — at 10× we throttle DB queries with adaptive sampling
- Filter by zone, person, alert type
- Pause + frame-step support
- Click a person dot → opens their `/analytics/persons/:id` page in a side drawer

### `/analytics/heatmap` — Zone heatmap

Floor plan with per-zone polygons coloured by intensity (dwell-seconds-per-zone over selected window). Legend shows scale. Time-window selector at top: today / week / month / custom.

### `/analytics/persons/:id` — Person profile

- Header: name, employee ID, department, last seen, photo
- 24h journey: horizontal timeline showing zone presence as coloured bars
- Per-zone dwell heatmap (last 7 / 30 days)
- Recent alerts involving this person
- "Open in timeline scrubber" CTA → loads timeline at the chosen 24h with this person filtered

---

## §8. Forensic CLIP search (`/forensic`)

Single-page, search-first:

```
┌──────────────────────────────────────────────────────────────────────┐
│  Forensic Search                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  person in red shirt seen near loading bay yesterday            │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  Time range: [Last 24h ▼]  Zone: [All ▼]  Camera: [All ▼]            │
│  ────────────────────────────────────────────────────────────────────│
│                                                                       │
│  Results (12 matches in 0.4s)                                        │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐                         │
│  │ [thumb]│ │ [thumb]│ │ [thumb]│ │ [thumb]│                         │
│  │ 14:23  │ │ 14:25  │ │ 14:38  │ │ 14:51  │                         │
│  │ Loading│ │ Loading│ │ Office │ │ Loading│                         │
│  │ score  │ │ score  │ │ score  │ │ score  │                         │
│  │ 0.83   │ │ 0.79   │ │ 0.71   │ │ 0.68   │                         │
│  └────────┘ └────────┘ └────────┘ └────────┘                         │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

Click a thumb → side drawer with 10s clip playback (HLS), tracklet metadata, and "Open in timeline at this moment" CTA.

Empty-state: "Try queries like 'person in red helmet', 'two people walking together', 'someone running'."

---

## §9. Admin view (`/admin`)

Light theme. Sidebar navigation; main pane is the active section.

| Section | Page | Notes |
|---|---|---|
| Dashboard | `/admin` | Worker health, GPU util, PostgreSQL write queue depth, Redis stream lag, latest schema migration, model versions |
| Persons | `/admin/persons` | List + enrolment wizard (4-step: name/ID → capture → quality check → save) |
| Cameras | `/admin/cameras` | List + add/edit; per-row "Run profiler" CTA, capability tier badge, calibration wizard launch |
| Zones | `/admin/zones` | Polygon editor on the floor-plan image; allowed_hours editor; max_capacity; loiter threshold |
| Users | `/admin/users` | CRUD + permission toggle matrix (zones × users) |
| Maintenance | `/admin/maintenance` | Calendar widget (Gantt) + create/edit/delete; one-time + cron |
| Anomaly detectors | `/admin/anomaly-detectors` | List of registered detectors; enable/disable toggle; per-detector config JSON editor with schema validation |
| Alert routing | `/admin/alert-routing` | Routing rule table + CRUD; test-fire button per rule (sends a test alert through the channel) |
| Models | `/admin/models` | Installed model versions; per-camera override editor; signed upload form for fine-tuned models |
| Audit | `/admin/audit` | Filterable log table; verify chain button; export PDF |

### Common admin patterns

- **Wizard steps** — multi-step modals with explicit progress indicator. "Cancel" requires confirmation if any field has been edited.
- **Inline edit + undo** — table cells become inputs on click; Esc cancels, Enter saves; toast with Undo for 6s.
- **Soft delete only** — destructive actions (deactivate camera, archive zone, delete user) require typed confirmation matching the entity name.

### `<HomographyCalibrator />` flow

```
Step 1: Pick camera          Step 2: Capture frame
Step 3: 4-point on frame     Step 4: 4-point on floor plan
Step 5: Compute + validate (reproj err < 2px or fail)
Step 6: Save
```

Live reprojection error displayed as user clicks; below 2px the Save button activates.

### `<MaintenanceCalendar />`

Month view with windows rendered as coloured bars. Hovering shows scope + duration + reason. Click a slot → "Create window" modal pre-filled with that timestamp. Click a bar → edit modal.

### `<ModelManager />`

```
Installed models                                       [+ Upload fine-tuned model]
─────────────────────────────────────────────────────────────────────────────────
SCRFD              v1.0.0        face_detection      [pinned]      [verify]
AdaFace IR50       v1.0.0        face_embedding      [pinned]      [verify]
                   acme_v2       face_embedding      [active on 1 camera ▼]
YOLOv8n person     v1.0.0        person_detection    [pinned]      [verify]
MoViNet violence   v1.0.0        violence            [pinned]      [verify]
CLIP-ViT-B/32      v1.0.0        forensic_search     [pinned]      [verify]

Per-camera overrides:
─────────────────────────────────────────────────────────────────────────────────
Camera             Face embedder            Violence       Thresholds
Loading Bay 1      adaface_ir50_acme_v2     default        scrfd_conf=0.55
Office HR Door     adaface_ir50_acme_v2     default        adaface_min_sim=0.78
[+ Add override]
```

---

## §10. Real-time integration

### Socket.io events (consolidated, extends v1 §11)

| Event | Direction | Payload | Throttling |
|---|---|---|---|
| `person_location` | server → client | `{global_track_id, person_id, camera_id, bbox, floor_x, floor_y, ts}` | 5fps per `global_track_id`, diff-only |
| `alert_fired` | server → client | `{alert_id, alert_type, severity, camera_id, zone_id, snapshot_url, ts}` | immediate |
| `alert_state_changed` | server → client | `{alert_id, new_state, actor_user_id, ts}` | immediate |
| `track_corrected` | server → client | `{global_track_id, new_person_id, ts}` | immediate |
| `camera_snapshot` | server → client | `{camera_id, url, ts}` | 2s per subscribed camera |
| `worker_health` | server → client | `{worker_id, status, cam_count, ts}` | on change |
| `head_count` | server → client | `{plant_total, by_zone: {[zone_id]: count}, ts}` | every 1s |
| `subscribe_camera` | client → server | `{camera_id}` | ad-hoc |
| `unsubscribe_camera` | client → server | `{camera_id}` | ad-hoc |
| `subscribe_track` | client → server | `{global_track_id}` | follow mode |
| `degraded_mode` | server → client | `{enabled: bool, reason: str}` | immediate |

### Reconnect rehydration

```ts
// src/shared/api/socket.ts
const socket = io(API_URL, {
  reconnection: true,
  reconnectionDelay: 500,
  reconnectionDelayMax: 5_000,
});

socket.on('connect', async () => {
  // 1. Fetch full state snapshot to reset stale UI
  const snapshot = await api.get('/api/state/snapshot');
  liveStore.reset(snapshot);
  // 2. Re-subscribe to user's selected camera/track
  const { focusedCameraId, followedTrackId } = liveStore.getState();
  if (focusedCameraId) socket.emit('subscribe_camera', { camera_id: focusedCameraId });
  if (followedTrackId) socket.emit('subscribe_track', { global_track_id: followedTrackId });
});

socket.on('disconnect', () => {
  liveStore.setState({ degraded: { connection: 'lost' } });
});
```

A persistent "Reconnecting..." banner appears 3s after disconnect; drops as soon as `connect` fires.

### Throttling on the client

`person_location` events arrive at 5fps from server. The store batches incoming events into a single render via `requestAnimationFrame` to avoid React re-renders per event:

```ts
const pendingUpdates = new Map<string, PersonLocation>();
let rafId = 0;
function queuePersonLocation(loc: PersonLocation) {
  pendingUpdates.set(loc.global_track_id, loc);
  if (!rafId) rafId = requestAnimationFrame(flush);
}
function flush() {
  rafId = 0;
  liveStore.applyLocations(Array.from(pendingUpdates.values()));
  pendingUpdates.clear();
}
```

### Degraded mode

When `degraded_mode` event arrives or WebSocket disconnects:

| Component | Behaviour |
|---|---|
| Camera grid | Continues polling JPEG snapshots via REST (every 5s instead of 2s to reduce load) |
| AlertSidebar | Shows "Alerts paused — system degraded" banner; existing alerts stay visible |
| FocusedCamera | HLS continues if it was already playing; bbox overlay frozen |
| HeadCount | Shows last-known value with a "stale" indicator |
| Floor plan | Person dots frozen at last position |

Once recovered: `liveStore.reset(snapshot)` re-syncs everything.

---

## §11. Client state (Zustand)

Three slices, each isolated:

### `liveStore` — guard view state

```ts
type LiveState = {
  cameras: CameraState[];
  focusedCameraId: number | null;
  followedTrackId: string | null;
  alerts: Alert[];
  trackedPersons: Map<string, PersonLocation>;  // global_track_id → location
  headCount: { total: number; byZone: Record<number, number> };
  degraded: { connection?: string; redis?: string } | null;

  // actions
  reset: (snapshot: StateSnapshot) => void;
  applyLocations: (locs: PersonLocation[]) => void;
  applyAlertFired: (alert: Alert) => void;
  applyAlertStateChanged: (id: number, state: AlertState) => void;
  setFocusedCamera: (id: number | null) => void;
  setFollowedTrack: (id: string | null) => void;
};
```

### `authStore` — current user, JWT, role

```ts
type AuthState = {
  user: User | null;
  token: string | null;
  login: (creds: LoginRequest) => Promise<void>;
  logout: () => void;
};
```

### `themeStore` — theme + i18n

```ts
type ThemeState = {
  theme: 'light' | 'dark';
  locale: 'en' | 'hi';
  toggleTheme: () => void;
  setLocale: (l: 'en' | 'hi') => void;
};
```

Stored in `localStorage` (theme, locale only — never JWT).

### Server state — TanStack Query

Used for everything fetched from REST: persons, cameras, zones, alerts (historical), forensic results, audit log, etc. Stale times tuned per endpoint:

| Endpoint | Stale time | Background refetch |
|---|---|---|
| `/api/persons/search` | 30s | yes |
| `/api/persons/:id` | 5min | on focus |
| `/api/cameras` | 5min | on focus |
| `/api/zones` | 5min | on focus |
| `/api/state/snapshot` | 0 (always refetch) | n/a |
| `/api/alerts/active` | 5s | yes |
| `/api/alerts/historical` | 30s | yes |
| `/api/audit/...` | 60s | manual |
| `/api/cameras/:id/snapshot` | n/a — direct img refresh, not via Query |

---

## §12. Forms & validation

Every form: `react-hook-form` + Zod schema co-located with the form component:

```tsx
// src/features/admin/components/EnrolmentForm.tsx
const schema = z.object({
  full_name: z.string().min(2).max(200),
  employee_id: z.string().regex(/^EMP-\d{3,6}$/),
  department: z.string().min(1),
  person_type: z.enum(['employee', 'contractor', 'visitor']),
});
type EnrolmentFormValues = z.infer<typeof schema>;

export function EnrolmentForm({ onSubmit }: Props) {
  const { register, handleSubmit, formState: { errors, isSubmitting } } =
    useForm<EnrolmentFormValues>({ resolver: zodResolver(schema) });

  return (
    <form onSubmit={handleSubmit(onSubmit)} aria-label="Employee enrolment form">
      <Input {...register('full_name')} label="Full name" error={errors.full_name?.message} />
      <Input {...register('employee_id')} label="Employee ID" error={errors.employee_id?.message} />
      ...
      <Button type="submit" loading={isSubmitting}>Save</Button>
    </form>
  );
}
```

Error messages rendered inline + `aria-invalid="true"` + `aria-describedby` linkage to the error text. Submit button shows loading spinner; form-level error toast on server failure (5xx).

### Validation rules summary

| Field | Rule |
|---|---|
| `full_name` | 2–200 chars |
| `employee_id` | Regex `^EMP-\d{3,6}$` (configurable per customer) |
| `email` | RFC-5322 regex |
| `password` | ≥12 chars, ≥1 upper, ≥1 lower, ≥1 digit, ≥1 symbol |
| `rtsp_url` | URL parse + `^rtsp://` prefix |
| `cron_expr` | parsed via `cron-parser` library; show next 3 fire times as a preview |
| `webhook_target` | URL parse + HTTPS required (HTTP allowed only with explicit confirm checkbox) |

---

## §13. Tables & virtualisation

Many admin lists can grow into thousands of rows. Use **TanStack Table** + `@tanstack/react-virtual` for any list >100 rows:

```tsx
const virtualizer = useVirtualizer({
  count: rows.length,
  getScrollElement: () => parentRef.current,
  estimateSize: () => 48,
  overscan: 8,
});
```

Tables that always need virtualisation:
- `/admin/audit` (audit log)
- `/admin/persons` (employee list)
- `/forensic` results (only when ≥100 results)

---

## §14. Accessibility

Target **WCAG 2.1 Level AA**. Specific requirements:

- All interactive elements reachable by keyboard. Tab order matches visual order.
- Focus rings always visible (Tailwind `focus-visible:ring-2 ring-brand-500`).
- Colour is never the only semantic carrier. Severity also shown via icon + label.
- All icons have `aria-label` or are decorative (`aria-hidden="true"`).
- `<video>` elements have caption tracks where available; live HLS has no captions but is decorative for guard scenarios.
- Form errors announced via `role="alert"`.
- Dialogs trap focus; Esc closes; restoring focus to the trigger on close.
- Toast notifications: live region with `aria-live="polite"`; critical toasts use `assertive`.
- Colour contrast minimum 4.5:1 for body, 3:1 for large text.
- Reduced motion (`@media (prefers-reduced-motion: reduce)`) collapses all non-essential animation to 0ms.
- All routes have a unique, descriptive `<title>` (set via `react-helmet-async`).

CI step: `pnpm test:a11y` runs axe-core against every page in storybook (Phase 4 task — `/storybook` not part of v1 ship but used for component dev).

---

## §15. Performance

### Budgets

| Metric | Target | Failure mode |
|---|---|---|
| Initial bundle (gzipped) | ≤ 800kB | CI fails build |
| Route bundle (gzipped) | ≤ 300kB | warning, then fail at 400kB |
| First Contentful Paint | ≤ 1.5s on i5-8th-gen, GbE | warning |
| Time-to-Interactive | ≤ 3s on same | warning |
| Largest Contentful Paint | ≤ 2.5s | warning |
| Cumulative Layout Shift | < 0.1 | fail at 0.25 |
| Floor-plan render with 50 person dots | ≤ 16ms per frame | warning at 32ms |

### Code splitting

- One bundle per top-level route via `React.lazy` + `Suspense`
- shadcn primitives in a shared chunk
- Recharts in `analytics` chunk only (it's heavy)
- Leaflet in chunks where it's used (admin/zones, analytics/heatmap, live/follow)
- HLS.js in `live` chunk

### Image strategy

- Camera snapshots: served as JPEG at 1280px max width (server-side resize). `<img loading="lazy">` for off-screen tiles
- Floor plan PNG: served once + cached in `<picture>` with WebP/AVIF fallback chain
- Person thumbnails: 192×192 JPEG, served via signed URL with 5min validity

### Render optimisation

- Memoise `<CameraTile>`, `<AlertCard>`, `<PersonDot>` (these can re-render thousands of times per minute otherwise)
- Use CSS transforms for live person dots, not React state-driven layout (subscribe directly to a Zustand selector + DOM mutation in a `useEffect`)
- Floor plan SVG: single `<g>` with one `<circle>` per active track; positions updated via direct DOM manipulation in an animation frame

---

## §16. Error boundaries & error UX

### Boundary hierarchy

```
<App>
  <ErrorBoundary fallback={<AppCrashScreen />}>
    <Providers>
      <Routes>
        <Route ...>
          <ErrorBoundary fallback={<RouteCrashScreen />}>
            <FeaturePage />
          </ErrorBoundary>
        </Route>
      </Routes>
    </Providers>
  </ErrorBoundary>
</App>
```

App-level boundary: full-page crash screen with "Reload", "Report issue", and the error fingerprint hash.
Route-level: in-place fallback so guard view stays operational if analytics page crashes.

### API error mapping

`shared/api/client.ts` maps HTTP status to typed error classes:

```ts
class ApiError extends Error {
  constructor(public readonly status: number, public readonly body: ApiErrorBody) { super(body.detail); }
}
class UnauthorizedError extends ApiError {} // 401
class ForbiddenError extends ApiError {}    // 403
class NotFoundError extends ApiError {}     // 404
class ValidationError extends ApiError {}   // 422
class ServerError extends ApiError {}       // 5xx
```

Top-level `useEffect` in `<App>` catches `UnauthorizedError` and redirects to `/login`.

### User-visible messages

| Error | UI |
|---|---|
| 401 | redirect to `/login` with `?next=...` |
| 403 | toast "You don't have permission for this action" + log to telemetry |
| 404 | inline empty state on lists; full `/404` page on direct nav |
| 422 | inline form errors mapped per-field |
| 5xx | toast "Server error — please retry. If it persists, contact support."; retry button on data fetches; auto-retry on background refetches |
| Network offline | persistent banner "No connection — retrying every 5s" |

---

## §17. Internationalisation

`react-intl` with messages keyed by feature:

```
src/shared/i18n/
├── index.tsx        # IntlProvider config
├── en/
│   ├── common.json
│   ├── live.json
│   ├── analytics.json
│   ├── admin.json
│   └── forensic.json
└── hi/              # Hindi added in v2.x
```

v1 ships with English only. Every UI string goes through `<FormattedMessage id="..." />` from day one, so adding Hindi later is a translation file, not a code change. Date/number formatting uses `Intl.DateTimeFormat` keyed to `themeStore.locale`.

---

## §18. Testing

### Unit + integration — Vitest + React Testing Library

Located alongside the component:

```
src/features/live/components/AlertCard.tsx
src/features/live/components/AlertCard.test.tsx
```

Coverage target: 80% for shared, 70% for features. Hooks tested in isolation; pages tested as integration with mocked API and socket.

### E2E — Playwright

`e2e/` directory. Three spec suites:
- `e2e/guard.spec.ts` — login as guard, see alerts, acknowledge, follow person
- `e2e/admin.spec.ts` — enrol person, calibrate camera, edit zone, create maintenance window
- `e2e/forensic.spec.ts` — search clips by text, open clip drawer

Runs against a docker-compose stack with FastAPI + PostgreSQL test DB pre-seeded.

### Visual regression — optional, Phase 4.x

Storybook + Chromatic for the design-system primitives (Button, Input, Modal, Toast). Not applied to pages in v1.

---

## §19. Build & dev tooling

```bash
# Dev
pnpm dev                  # Vite dev server on :5173, proxies /api → :8000
pnpm test                 # Vitest watch
pnpm test:run             # Vitest CI
pnpm test:e2e             # Playwright (requires docker-compose up)
pnpm test:a11y            # axe-core against storybook
pnpm lint                 # eslint + prettier --check
pnpm typecheck            # tsc --noEmit

# Build
pnpm build                # Vite production build → dist/
pnpm preview              # serve dist/ locally to verify
```

Production deployment: FastAPI mounts `frontend/dist/` at `/` via `StaticFiles`; React Router uses HTML5 history mode with FastAPI catch-all serving `index.html` for SPA routes.

---

## §20. Frontend phase plan

This spec is implemented in **Phase 4** of the v2 plan (`§K Phase 4 — Frontend`). Suggested decomposition into sub-plans:

| Sub-plan | Scope | Estimated tasks |
|---|---|---|
| 4A. Scaffold & design system | Vite scaffold, Tailwind, tokens, primitive components, layout shells | ~10 tasks |
| 4B. Auth + routing + role guards | Login flow, JWT handling, RoleGuard, route table, 403/404 pages | ~6 tasks |
| 4C. Live (Guard) view | TopBar, CameraGrid, FocusedCamera, AlertSidebar, HeadCountBanner, FollowPerson | ~14 tasks |
| 4D. Analytics + forensic | Timeline scrubber, heatmap, person profile, forensic search | ~12 tasks |
| 4E. Admin views | Enrolment wizard, camera config + profiler trigger, zone editor, maintenance calendar, model manager, audit viewer | ~16 tasks |
| 4F. Real-time integration | Socket.io setup, throttling, reconnect rehydration, degraded UX | ~6 tasks |
| 4G. E2E + a11y + perf budget | Playwright suites, axe-core in CI, Lighthouse budget gates | ~8 tasks |

Total: ~72 tasks across 7 sub-plans. Each sub-plan independently shippable.

---

**End of frontend design specification.**
