# VMS Enterprise Interaction Guidelines
**Design Specification** · 2026-07-06
**Status:** Draft
**Companion:** `docs/frontend/2026-06-24-vms-design-system.md` (tokens, component patterns)

> This spec defines how the VMS *behaves*, not just how it looks. It covers motion, loading, status language, alarm workflows, operator efficiency, and the full interaction model that separates a surveillance platform from a generic dashboard.

---

## 1. Operator Mental Model

Three principles govern operator interaction design:

1. **Alarm primacy.** Every screen and every interaction is subordinate to the alarm. An operator in an active alarm must be able to acknowledge, act, and close within 30 seconds without leaving the screen they're on.

2. **Operational language over generic language.** "Recording" beats "Online." "Reconnecting" beats "Degraded." "Unauthorized" beats "Auth Failed." Every status, every label, every button must describe what the *system is doing*, not what state it's *abstractly in*.

3. **Never animate live telemetry.** Camera feeds, head-count numbers, person dots, FPS counters — these update in real time. Animating their transitions obscures changes rather than highlighting them. Motion is reserved for navigation and structural transitions.

---

## 2. Motion Specification

### 2.1 Duration table

| Interaction type | Duration | Easing | Notes |
|---|---|---|---|
| Hover state (color, shadow) | 100 ms | `ease-out` | Feels instant; any longer is sluggish |
| Dropdown / popover appear | 120 ms | `ease-out` | Opacity + 4px translateY |
| Page fade transition | 120 ms | `ease-in-out` | Opacity only; no slide on page change |
| Accordion expand/collapse | 150 ms | `ease-in-out` | Height transition |
| Sidebar open/close | 180 ms | `cubic-bezier(0.2,0,0,1)` | Emphasized slide |
| Modal enter | 180 ms | `cubic-bezier(0.2,0,0,1)` | Scale 0.96 → 1 + opacity |
| Toast slide-in | 200 ms | `cubic-bezier(0.2,0,0,1)` | From right |
| Card hover shadow | 100 ms | `ease-out` | Shadow-1 → shadow-2 |
| Tab indicator slide | 200 ms | `cubic-bezier(0.2,0,0,1)` | Sliding underline |
| Skeleton → content | 0 ms | — | No fade; instant swap reduces shift |
| Chart initial render | 0 ms | — | **Never animate chart data** |
| Chart data refresh | 0 ms | — | Instant update — animate = operator confusion |
| Telemetry values | 0 ms | — | Head count, FPS, bitrate — instant |
| Alert severity flash | 600 ms one-shot | `ease-out` | Background flash only, never pulse |

### 2.2 CSS variables

```css
:root {
  --duration-instant:  0ms;
  --duration-fast:     100ms;
  --duration-quick:    120ms;
  --duration-base:     180ms;
  --duration-slow:     200ms;
  --duration-flash:    600ms;

  --easing-standard:   cubic-bezier(0.4, 0, 0.2, 1);
  --easing-emphasized: cubic-bezier(0.2, 0, 0, 1);
  --easing-exit:       cubic-bezier(0.4, 0, 1, 1);
}
```

### 2.3 `prefers-reduced-motion`

All durations collapse to `0.01ms`. Opacity fades remain (structural, not decorative). Status pulse (`animate-status-pulse`) is disabled. No exceptions.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
  .animate-status-pulse { animation: none; }
}
```

---

## 3. Loading & Skeleton Behavior

**Rule:** Never show a spinner for structured content. Use a skeleton that matches the shape of the loading content. Spinners are only for full-page loads or within a button during a form submission.

### 3.1 Skeleton definitions per component

**Camera card (in grid or list):**
```
┌──────────────────────────────┐  h: 160px, rounded-xl
│  ██████████████████████████  │  thumbnail: w-full h-32 bg-surface-raised animate-pulse rounded-[10px]
│  ░ ████████ · ████████ ░░░░  │  label bar: h-3 w-2/3 bg-surface-raised animate-pulse mt-2
└──────────────────────────────┘
```

**Person list row:**
```
[●●●] [████████████  ████████████]  [██████]
  40px avatar  2/3 width name     1/4 width ID
  h-4 rounded-full                h-3 rounded
```

**Alert card skeleton:**
```
[████]  [████████████████████]  [██████]
 4px    severity label + loc     time
border  h-4 w-1/2               h-3 w-20
```

**Analytics KPI card:**
```
[████████████]   number: h-8 w-24 rounded-lg
[████████████████████]  label: h-3 w-full mt-2
```

**Timeline scrubber:**
```
[████████████████████████████████████████]  h-8 w-full rounded-lg
[████]  [████]  [████]  [████]             4 event markers h-3 w-10
```

**Audit log row:**
```
[████████████]  [██████████████]  [████████████████]  [████]
  timestamp        event type          detail          user
  w-28 h-3         w-24 h-3           w-1/2 h-3        w-16 h-3
```

**Dashboard service health grid:**
```
[████████]         label: h-4 w-20
[████████████████] status text: h-3 w-32
```

### 3.2 Skeleton rules

- Repeat N rows equal to the expected page size (use 8 for admin list, 4 for dashboard cards).
- `prefers-reduced-motion`: replace `animate-pulse` with static `bg-surface-raised opacity-50` — no motion.
- Once data arrives: instant swap. No fade. React state swap is fast enough.
- Never combine a spinner AND a skeleton in the same loading context — pick one.
- `aria-busy="true"` on the container while loading; remove when content is present.

### 3.3 Spinner usage (reserved cases only)

| Context | Use |
|---|---|
| Button submitting a form | Inline 16px spinner, replaces leading icon, `aria-busy` |
| Full page initial load (AppShell) | Centered 32px spinner on surface-base |
| Modal action in progress | Inline spinner in confirm button |
| Any structured list or grid | **Never** — use skeleton |
| Charts / timeline | **Never** — show last data until new data arrives |

---

## 4. Status Language

### 4.1 Camera operational status — 10 states

Replace the legacy 4-state model. These states are mutually exclusive and ordered by operational priority.

| State | Label | Color | Icon | Description |
|---|---|---|---|---|
| `recording` | Recording | `green-600` | `Radio` | Actively writing to storage + streaming AI |
| `streaming` | Streaming | `green-500` | `Play` | Streaming to viewers; storage paused (e.g., motion-gate inactive) |
| `connected` | Connected | `green-400` | `CheckCircle2` | Reachable, not yet streaming (startup / standby) |
| `analytics` | Analytics | `blue-500` | `Cpu` | AI pipeline running; video feed degraded but analytics active |
| `maintenance` | Maintenance | `blue-400` | `Calendar` | Maintenance window active; expected offline |
| `standby` | Standby | `gray-400` | `Moon` | Healthy but idle; stream not requested |
| `reconnecting` | Reconnecting | `amber-500` | `RefreshCw` | Connection lost, actively retrying |
| `unauthorized` | Unauthorized | `amber-600` | `ShieldX` | RTSP credentials invalid |
| `unreachable` | Unreachable | `gray-500` | `WifiOff` | No network path; not retrying |
| `offline` | Offline | `gray-500` | `XCircle` | Gracefully stopped or disabled |
| `recovering` | Recovering | `amber-400` | `Activity` | Reconnected; restarting analytics pipeline |
| `disabled` | Disabled | `gray-300` | `MinusCircle` | Manually disabled by admin; not monitored |

**Badge rendering:**

```tsx
const CAMERA_STATUS_CONFIG: Record<CameraStatus, {
  label: string; colorClass: string; iconName: LucideIconName; pulse: boolean;
}> = {
  recording:    { label: 'Recording',    colorClass: 'text-green-600',  iconName: 'Radio',       pulse: true  },
  streaming:    { label: 'Streaming',    colorClass: 'text-green-500',  iconName: 'Play',        pulse: true  },
  connected:    { label: 'Connected',    colorClass: 'text-green-400',  iconName: 'CheckCircle2',pulse: false },
  analytics:    { label: 'Analytics',    colorClass: 'text-blue-500',   iconName: 'Cpu',         pulse: false },
  maintenance:  { label: 'Maintenance',  colorClass: 'text-blue-400',   iconName: 'Calendar',    pulse: false },
  standby:      { label: 'Standby',      colorClass: 'text-gray-400',   iconName: 'Moon',        pulse: false },
  reconnecting: { label: 'Reconnecting', colorClass: 'text-amber-500',  iconName: 'RefreshCw',   pulse: true  },
  unauthorized: { label: 'Unauthorized', colorClass: 'text-amber-600',  iconName: 'ShieldX',     pulse: false },
  unreachable:  { label: 'Unreachable',  colorClass: 'text-gray-500',   iconName: 'WifiOff',     pulse: false },
  offline:      { label: 'Offline',      colorClass: 'text-gray-500',   iconName: 'XCircle',     pulse: false },
  recovering:   { label: 'Recovering',   colorClass: 'text-amber-400',  iconName: 'Activity',    pulse: true  },
  disabled:     { label: 'Disabled',     colorClass: 'text-gray-300',   iconName: 'MinusCircle', pulse: false },
};
```

Pulse is only applied on genuinely-active states (recording, streaming, reconnecting, recovering) — never on alarm/warning states.

### 4.2 Operational language — preferred terms

| Avoid | Use instead |
|---|---|
| Online | Recording · Streaming · Connected |
| Offline | Offline · Unreachable · Disabled |
| Healthy | Recording · Connected |
| Ready | Streaming |
| Good | Connected |
| Working | Recording |
| Auth Failed | Unauthorized |
| Degraded | Reconnecting · Recovering |
| Error | Fault (with error code) |

### 4.3 Service health language

| Avoid | Use |
|---|---|
| OK | Running |
| Healthy | Running |
| Up | Connected |
| Down | Faulted |
| Unknown | Unreachable |

---

## 5. Alarm System

### 5.1 Severity model

Five levels, ordered ascending:

| Level | Label | Color | Icon | Response SLA | Auto-escalate after |
|---|---|---|---|---|---|
| 0 | Information | gray-500 | `Info` | None | Never |
| 1 | Low | green-600 | `InfoCircle` | 24 hours | 36 hours |
| 2 | Medium | amber-500 | `AlertCircle` | 4 hours | 6 hours |
| 3 | High | orange-600 | `AlertTriangle` | 1 hour | 90 minutes |
| 4 | Critical | `#dc2626` | `ShieldAlert` | 15 minutes | 20 minutes |

**Severity critical uses `#dc2626` exclusively.** This is the same bright red used throughout the system for danger signals. It must never be confused with brand color.

### 5.2 Alarm anatomy

Every alarm record carries:

```ts
interface Alarm {
  id: string;
  severity: 0 | 1 | 2 | 3 | 4;
  alarm_type: AlarmType;        // INTRUSION | VIOLENCE | LOITERING | UNKNOWN_PERSON | PPE | SYSTEM_CRITICAL
  source_camera_id: string | null;
  source_zone_id: string | null;
  person_gid: string | null;    // null for system alarms
  fired_at: string;             // ISO UTC
  acknowledged_at: string | null;
  acknowledged_by: string | null;  // user_id
  assigned_to: string | null;      // user_id — operator owns it
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_notes: string | null;
  sla_deadline: string;         // computed: fired_at + SLA for this severity
  escalation_status: 'none' | 'warning' | 'breached' | 'escalated';
  escalated_to: string | null;  // user_id
}
```

### 5.3 Alarm lifecycle / state machine

```
FIRED
  │
  ├─── Operator acknowledges ──────────────────────────► ACKNOWLEDGED
  │       (removes from "new" queue; operator is now owner)      │
  │                                                               │
  ├─── SLA 50% elapsed (unacknowledged) ──► SLA WARNING          │
  │                                                               │
  ├─── SLA elapsed (unacknowledged) ──────► ESCALATED            │
  │                                         (notify supervisor)  │
  │                                                               │
  └───────────────────────────────────────────────────────────► RESOLVED
                                                   (operator closes with notes)
```

### 5.4 Alarm card UI (detail)

```
┌─[4px severity border color]────────────────────────────────┐
│ ⚡ HIGH  ·  Intrusion Detected          4 min 32 sec ago   │
│ Cam-07 · North Loading Dock · Zone B                        │
│ SLA: 56 min remaining  [████████████████░░░░] 78%          │
│                                                             │
│ Assigned to: Unassigned                                     │
│ Escalation: None                                            │
│                                                             │
│ [ Acknowledge + Assign to Me ]   [ View Camera ]           │
│ ▸ +2 similar in this zone (expand)                         │
└─────────────────────────────────────────────────────────────┘
```

- SLA bar: `bg-action-700` fill, turns amber at < 25%, red at < 10%
- Acknowledged bar shows operator name + time since ack
- "View Camera" opens the focused camera view immediately
- "Acknowledge + Assign to Me" is always the primary action — one click, no modal

### 5.5 SLA escalation behavior

When SLA is breached (unacknowledged):
1. Alarm card gains a pulsing amber border (`animate-status-pulse` with amber color)
2. Alert count badge in TopBar gains an `!` indicator
3. If supervisor is configured: system emits a notification via the configured alert-routing channel
4. After a further 50% of SLA elapsed: second escalation to admin (if configured)

Do NOT use bright red for the SLA warning — red is reserved for the alarm severity itself. Use amber for SLA states.

---

## 6. Camera Health Score

A single calculated score (0–100%) gives operators an at-a-glance camera quality indicator without reading individual metric rows.

### 6.1 Score calculation

| Check | Weight | Pass condition |
|---|---|---|
| Recording | 20% | `status == 'recording'` |
| FPS | 15% | `current_fps >= target_fps * 0.9` |
| Bitrate | 15% | `bitrate within ±20% of target` |
| Storage | 15% | `storage_remaining_days >= 3` |
| Network | 10% | `packet_loss < 1%` |
| AI pipeline | 15% | `inference_latency_ms < 100` |
| Time sync | 5% | `ntp_offset_ms < 500` |
| Calibration | 5% | `homography_error_px < 2.0` |

Score = sum of weights for passing checks.

```ts
function computeCameraHealthScore(health: CameraHealthData): number {
  let score = 0;
  if (health.status === 'recording') score += 20;
  if (health.current_fps >= health.target_fps * 0.9) score += 15;
  if (Math.abs(health.bitrate_kbps - health.target_bitrate_kbps) / health.target_bitrate_kbps < 0.2) score += 15;
  if (health.storage_remaining_days >= 3) score += 15;
  if (health.packet_loss_pct < 1) score += 10;
  if (health.inference_latency_ms < 100) score += 15;
  if (Math.abs(health.ntp_offset_ms) < 500) score += 5;
  if (health.homography_error_px < 2.0) score += 5;
  return score;
}
```

### 6.2 Score display

```
Camera Health
┌──────────────────────────────────┐
│ 96%  ████████████████████████░░  │
│                                  │
│ ✔ Recording    ✔ FPS (24/25)     │
│ ✔ Bitrate      ✔ Storage (14d)   │
│ ✔ Network      ✔ AI (48ms)       │
│ ✔ Time Sync    ✗ Calibration     │
└──────────────────────────────────┘
```

Score thresholds:
- 90–100%: green, "Excellent"
- 70–89%: green-400, "Good"
- 50–69%: amber, "Degraded"
- < 50%: orange-600, "Fault"
- 0%: gray, "Offline"

The score ring / bar uses `action-700` color (not red). A low score is not an alarm — it is a maintenance signal.

---

## 7. Operator Workflow

### 7.1 Primary alarm response sequence

This is the workflow every guard completes dozens of times per shift. Every step must be reachable with ≤ 2 clicks and ≤ 1 keyboard shortcut.

```
1. ALARM FIRES
   ↓
2. Alarm appears in sidebar (auto-scroll to top, flash animation)
   ↓
3. Operator clicks alarm card
   → Camera view opens to the source camera instantly
   → Timeline scrubs to alarm timestamp (T-5s pre-roll)
   ↓
4. Operator reviews the event
   → Can scrub ±60s in timeline
   → Can pause, step frame, zoom in
   ↓
5. Operator bookmarks key frames (Keyboard: B)
   ↓
6. Operator exports clip (Keyboard: E)
   → Clip export dialog: start/end range, format, destination
   → Export queued; operator does not wait
   ↓
7. Operator acknowledges alarm (Keyboard: A)
   → Acknowledgement logged with timestamp + user
   → Alarm moves from "New" to "In Progress"
   ↓
8. Operator adds incident note (optional, Keyboard: N)
   ↓
9. Operator assigns incident to case (optional)
   ↓
10. Operator resolves alarm (Keyboard: R)
    → Resolution requires a reason (dropdown: False Positive | Investigated | Escalated | Other)
    → Audit log entry written
    → Alarm moves to RESOLVED
    → Next unacknowledged alarm auto-surfaces
```

### 7.2 Keyboard shortcuts — operator tier

| Key | Action | Context |
|---|---|---|
| `A` | Acknowledge focused alarm | Alert sidebar focused |
| `R` | Resolve focused alarm | Alert sidebar focused |
| `B` | Bookmark current frame | Camera view |
| `E` | Open export clip dialog | Camera view |
| `N` | Open incident note | Camera view or alert card |
| `Space` | Play / Pause timeline | Timeline focused |
| `←` / `→` | Step 5 seconds back/forward | Timeline |
| `Shift+←` / `Shift+→` | Step to previous/next alarm event | Timeline |
| `F` | Follow person | Person dot selected |
| `Esc` | Close camera focus, return to grid | Camera view |
| `1`–`9` | Switch to camera N in grid | Camera grid |
| `Cmd+K` | Person search (command palette) | Global |
| `Cmd+M` | Toggle map/grid view | Guard view |

All shortcuts:
- Documented in a keyboard shortcut legend (`?` key opens it)
- Never conflict with browser defaults
- Screen-reader safe (shortcuts only active when guard view is focused)

### 7.3 Multi-monitor layout guidelines

The VMS should support three named layout profiles. Profiles persist per user.

| Profile | Description | Layout |
|---|---|---|
| **Single** | 1 monitor, default. Full app in one window. Guard view occupies center. | Standard 3-column |
| **Dual** | 2 monitors. Monitor 1: camera grid + alert sidebar. Monitor 2: focused camera + timeline. | Split SPA windows |
| **Wall** | 1 large display (55"+ or video wall). Grid-only mode, max cameras visible, no sidebar. Status bar at bottom. | Full-bleed grid, sidebar off |

For Dual and Wall, a `layout` URL param drives the view:
- `?layout=dual-primary` — camera grid + sidebar
- `?layout=dual-secondary` — focused camera + timeline
- `?layout=wall` — full-screen grid, configurable N×M

---

## 8. Live Video Behaviors

### 8.1 HLS stream controls

| Action | Behavior |
|---|---|
| Click camera in grid | Opens to focused view (center panel); grid remains visible |
| Double-click in focused | Enter full-screen (CSS `element.requestFullscreen()`) |
| Hover focused camera | Show controls overlay (bottom bar): play/pause, volume, full-screen, timeline |
| Controls auto-hide | After 3s inactivity during playback |
| Click camera dot on floor plan | Same as clicking camera tile |
| Drop stream | Show last frame + amber "Reconnecting…" overlay; retry every 5s |

### 8.2 Timeline scrubber behavior

- Default: tracks live edge (rightmost position)
- Clicking a past point: pauses live, loads VOD segment, shows red "LIVE" button to return
- Alarm markers: clickable; clicking jumps to T-5s before alarm event
- Bookmarks: yellow markers, hoverable (shows label + time)
- Segment boundaries (recording gaps): gray bars in timeline track
- Export range: drag-select a range in the timeline → triggers clip export

### 8.3 Bounding box overlay

- Rendered as SVG over the video `<canvas>` or as absolute-positioned divs
- Update throttle: **5 fps** (not 30fps — visual clarity over precision)
- Colors: known person = `brand-crimson` dot with name label, unknown = red, followed = yellow
- Person count: top-right badge, updates via socket event `head_count`
- Position updates via CSS `transform: translate(x, y)` — no React re-render for each frame

---

## 9. Auditability

Every operator action on a surveillance system must be traceable. The audit log is already implemented; this section defines what the **UI must expose** for each event.

### 9.1 Required audit fields (visible in audit table)

| Field | Description |
|---|---|
| Timestamp | ISO UTC, rendered in user's local timezone |
| Operator | Full name + role |
| Camera | Camera name + ID (if applicable) |
| Action | Specific action type (Acknowledged, Resolved, Exported Clip, Viewed Person, GDPR Purged…) |
| Reason | Operator-supplied reason (required for resolution, purge, config change) |
| Outcome | Success / Failed / Pending |
| IP Address | Client IP at time of action |
| Session ID | For correlating actions within one shift |

### 9.2 Audit export

Operators with Manager+ role can export the audit log as:
- **CSV** — all columns, date range filtered
- **PDF** — signed PDF with hash-chain verification summary

Audit export action is itself audited (meta-audit).

---

## 10. Error Handling

### 10.1 Error presentation strategy

Not all errors are equally urgent. The display tier matches the severity:

| Error type | Display | Duration |
|---|---|---|
| Form validation (field-level) | Inline below field, red text, red border | Until corrected |
| Form submission failure | Inline error banner above form CTA | Until dismissed |
| API request failure (non-critical) | Toast — error variant | Manual dismiss |
| Stream connection failure | Overlay on the specific camera tile | While failing |
| WebSocket disconnect | Top-of-page reconnection banner | While disconnected |
| Service down (API/DB/Redis) | System health card on dashboard + toast | While down |
| Critical system fault | Full-screen error state with retry | Until resolved |
| Alarm SLA breach | Alarm card badge + sidebar badge | Until alarm resolved |

### 10.2 Offline and reconnect behavior

**WebSocket disconnects:**
1. Immediately: show a non-blocking "Reconnecting…" bar at the top of the screen (amber background, `RefreshCw` icon)
2. After 5s: upgrade bar to warning — "Live updates paused — attempting to reconnect"
3. On reconnect: `GET /api/state/snapshot` → reset in-memory state → re-subscribe to camera/track
4. Show a success toast: "Reconnected — data refreshed" (auto-dismiss 3s)
5. Never clear the alarm sidebar on disconnect — stale alarms are better than empty alarms

**API failures:**
- Non-retried `4xx` (except 429): show inline error, do not retry
- `5xx` and `429`: exponential back-off retry (1s, 2s, 4s, max 3 retries), then show error
- `401` anywhere: redirect to `/login` with `?reason=session_expired`

### 10.3 Forbidden error patterns

- **Never show a raw error stack trace** in production UI — sanitize error messages
- **Never show "Something went wrong"** without a specific action the user can take
- **Never clear form state** after an API error — the user's entered data must be preserved
- **Never auto-redirect** on a non-auth error — the user may have unsaved changes

---

## 11. Performance Budgets

| Metric | Budget | Measured by |
|---|---|---|
| Initial JS bundle | ≤ 800 kB gzipped | `bundlesize` CI gate |
| Route chunk | ≤ 300 kB gzipped | `bundlesize` CI gate |
| LCP (Largest Contentful Paint) | ≤ 2.5s | Lighthouse CI |
| FID (First Input Delay) | ≤ 100ms | Lighthouse CI |
| CLS (Cumulative Layout Shift) | ≤ 0.1 | Lighthouse CI |
| Alert delivery latency (socket → on-screen) | ≤ 250ms | E2E timing test |
| Camera grid render (12 tiles) | ≤ 200ms | React profiler |
| Floor plan dot update (52 persons) | ≤ 16ms | rAF timing |
| API p95 response time | ≤ 300ms | API monitoring |

---

## 12. Accessibility

### 12.1 Targets

WCAG 2.1 AA for all views. Guard view additionally targets:
- High-contrast mode compatibility (`forced-colors: active` media query)
- Screen reader announcement of new alarms (`aria-live="assertive"`)
- All alarm controls reachable by keyboard (no mouse required to acknowledge)

### 12.2 Focus management

- Modal opens: focus moves to first interactive element (Cancel, not the destructive action)
- Modal closes: focus returns to the trigger element
- New alarm: focus is NOT moved (operator may be in the middle of another interaction — do not interrupt)
- Toast: focus is NOT moved (polite/assertive `aria-live` announces it)
- Route change: focus moves to the `<main>` landmark (skip-nav link for keyboard users)

### 12.3 Required landmarks

Every page must have exactly one `<main>` element. Sidebar nav must be inside `<nav aria-label="Primary navigation">`. Alert sidebar must be `<aside aria-label="Active alerts">`.

---

## 13. Responsive & Multi-Resolution

### 13.1 Supported configurations

| Configuration | Min resolution | Notes |
|---|---|---|
| Single desktop | 1280×800 | Minimum supported; 1440×900 recommended |
| Dual desktop | 2× 1920×1080 | Use layout profiles (§7.3) |
| Control room wall | 3840×2160 (4K) or video wall | Wall layout profile |
| Laptop | 1280×800 | Sidebar collapses to icons at < 1440 |

No mobile or tablet support in v1.

### 13.2 Breakpoints

| Name | px | What changes |
|---|---|---|
| `xl` | 1440px | Guard alert sidebar expands from icon-strip (64px) to full (380px) |
| `lg` | 1280px | Admin sidebar collapses; display type steps down 4px |
| (none below `lg`) | — | Not targeted in v1 |

---

**End of VMS Enterprise Interaction Guidelines.**
