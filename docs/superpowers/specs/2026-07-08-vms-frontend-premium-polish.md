# VMS Frontend Premium Polish & Data Completeness
**Design Specification** · 2026-07-08
**Status:** Approved (open questions resolved 2026-07-08, see §13)

---

## 1. Purpose & scope

The frontend is functionally broad (Phases 4A–4M shipped 805 tests across live, admin,
analytics, forensic, auth) but does not yet read as a **premium SaaS product**. Two audits
(2026-07-08) found the gaps fall into exactly two buckets:

1. **Design-language debt** — hardcoded colors, typography fragmentation, parallel
   components, three different theme-scoping mechanisms, an oversized third-party sidebar,
   and missing loading/error/empty states on several routes.
2. **Data hollowness** — pages and widgets that render but are fed by nothing: the
   analytics dashboard queries two endpoints that don't exist, the TopBar GPU gauge is
   hardcoded to 0, three frontend calls 404, and seven working backend endpoints have no
   UI consumer.

This spec defines the target state for both. It is the **parent spec** for the remaining
frontend phases; each Part below becomes one plan file (§14). The earlier "Phase 4N"
sketch (minimal sidebar, dark-token audit, compact camera tiles) is absorbed here as
Part II.

**In scope:** design-language consolidation, component unification, app-shell/theme
architecture, UI-state doctrine, premium-feel details, the new backend endpoints needed
to populate existing UI, and wiring of orphaned endpoints.

**Out of scope:** HLS/recording playback (owned by `2026-06-12-vms-recording-clips-analytics.md`),
CLIP forensic text search (blocked on model deployment), PTZ control (needs ONVIF spec),
any identity/threshold logic, any new business features not already stubbed in the UI.

**Companion documents** (this spec amends, never forks):
- `docs/frontend/2026-06-24-vms-design-system.md` — token additions in §4 land there as amendments
- `docs/frontend/2026-05-01-vms-frontend-spec.md` — route/state/perf rules unchanged
- `docs/superpowers/specs/2026-07-06-vms-enterprise-interaction-guidelines.md` — operator
  workflow spec; Part III's offline/error doctrine must not contradict it

---

## 2. Design language principles

The reference class is modern operations SaaS: **Linear** (keyboard-first, dense,
instant), **Stripe/Vercel dashboards** (restrained neutral surfaces, one accent used
sparingly, impeccable typography), **Datadog/Grafana** (dark ops consoles that stay
legible for 8-hour shifts). From these, five binding principles:

| # | Principle | Concrete meaning here |
|---|---|---|
| P1 | **One accent, used scarcely** | Brass (`--brand-accent`) appears only at: logo, active-nav indicator, primary CTA per view, brand moments (login, empty-state icons). Never on focus rings, borders-at-rest, or body text. Already enforced by the §T restraint CI gate — keep it. |
| P2 | **Tokens are the only color vocabulary** | Zero hex literals and zero Tailwind palette classes (`slate-*`, `amber-*`, `white`, `black/*`) in feature code. Everything routes through `--surface-*`, `--text-*`, `--border-*`, `--severity-*`, `--status-*`. |
| P3 | **Density with hierarchy** | Operators scan, they don't read. Tight 8-token type scale, tabular numerals for every count/time, 4px-grid spacing. No decorative whitespace inflation, no cramping either. |
| P4 | **Keyboard-first, mouse-optional** | Cmd+K reaches everything; every workflow in the shortcut legend; `:focus-visible` ring on every interactive element. |
| P5 | **States are designed, not defaulted** | Every route ships loading (skeleton), empty (EmptyState + CTA), error (retry affordance), and degraded/offline designs. A blank panel is a defect. |

---

## 3. Current-state problem inventory (audit, 2026-07-08)

### 3.1 Design debt

| Problem | Evidence | Severity |
|---|---|---|
| Hardcoded dark hex colors | `LivePage.tsx` (5×), `CameraTile.tsx` (8×), `AlarmCard.tsx` (8×), `CameraTree.tsx` — `#0a0e1a #111827 #1a2234 #1e293b #232d42 #334155` | Critical |
| Tailwind palette creep | 11+ uses of `text-slate-*`, `text-white`, `bg-black/30`, `bg-amber-400` in live feature | Critical |
| Typography fragmentation | 9 distinct arbitrary `text-[Xpx]` sizes, 68+ usages; `text-[20px]`/`text-[22px]` invent sizes not in the scale | High |
| Parallel alert cards | `AlertCard.tsx` (token-clean, minimal) vs `AlarmCard.tsx` (feature-rich, token-dirty) with identical props | High |
| Three theme-scoping mechanisms | scoped `data-theme` attr (AdminLayout, LivePage, ForensicSearchPage) vs `useRouteTheme()` hook (now unused) vs none (error pages) | Medium |
| Oversized shadcn sidebar | ~750 lines + button/input/skeleton/tooltip compat files for a nav we use 20% of | Medium |
| Raw `<button>`/`<input>` bypassing design system | `AlertCard.tsx`, `ForensicSearchPage.tsx` (4 raw inputs), `AnalyticsDashboardPage.tsx` quick links | Medium |
| `focus:` instead of `focus-visible:` | `ForensicSearchPage.tsx:74` | Medium |
| Missing UI states | LivePage (no camera-empty, no stream-error), Analytics (kpiError captured, never rendered), FocusedCamera (no video-failed state) | Medium |
| Camera tiles overflow tree panel | full card tile (header+snapshot+body) forced into a 22%-width sidebar | Fixed 2026-07-08 (grid-cols-2), proper redesign in Part II |

### 3.2 Data hollowness

| Problem | Evidence |
|---|---|
| Frontend calls that 404 | `GET /api/persons/{id}` (PersonProfilePage), `POST /api/forensic/export` (ClipExportDialog), `GET /api/cameras/{id}/hls/index.m3u8` (FocusedCamera — deferred to recording spec) |
| Analytics endpoints don't exist | `GET /api/analytics/kpi`, `GET /api/analytics/head-count?days=7` — dashboard KPIs and chart query nothing |
| Fake telemetry | TopBar `gpuPct` initialized to 0, never updated; camera "uptime" computed from static `is_active` flag |
| Users CRUD absent | `AdminUsersPage` renders "Coming Soon"; no `/api/users` routes despite `User` model existing |
| Bookmarks are client-only | lost on refresh; no persistence endpoints |
| Orphaned backend endpoints (built, unconsumed) | `GET /api/anomaly-detectors/health`, `GET /api/maintenance/calendar`, `GET /api/sites/readiness-report.pdf`, `GET /api/forensic/clips/{id}`, `POST /api/cameras/{id}/recalibrate-required`, `POST /api/persons/{id}/embeddings` |
| Dead placeholder actions | CameraTile FAB: Playback / PTZ / Bookmark all `onClick: () => {}` |

---

## 4. Part I — Design language consolidation

### 4.1 Dark-surface token completion

The hardcoded live-view hexes are mostly *existing dark-theme token values* typed by hand
(`#0a0e1a` = dark `--surface-base`, `#111827` = dark `--surface-raised`, `#1f2937` ≈
`--border-default`). Two values have **no token**: `#1a2234` (card/tile background) and
`#232d42` (chip/inset background). Amend the design system §6.1 with one new surface pair,
defined in both themes:

```css
[data-theme='light'] {
  --surface-card: #ffffff;      /* card on raised background — same as base in light */
  --surface-chip: #e2e8f0;      /* chips, inset pills */
}
[data-theme='dark'] {
  --surface-card: #1a2234;      /* camera tiles, alarm cards */
  --surface-chip: #232d42;      /* tier badges, SLA track, inset pills */
}
```

Rules:
- Every `#hex` and palette class in `src/features/live/` is replaced by a token. The
  file-by-file mapping (from the audit) is mechanical: `#1e293b → border` (dark value
  `#1f2937` differs by 1 step — unify on `--border-default`; visual delta is imperceptible),
  `#334155 → border-strong`, `text-slate-100/200 → text-primary`, `text-slate-300/400 →
  text-secondary`, `text-slate-500/600 → text-muted`, `text-white → text-inverse`,
  `bg-amber-400 → var(--status-auth-failed)`, `#22c55e → var(--status-online)`.
- `bg-black/30` (tile header scrim) becomes a token: `--overlay-tile: rgba(0,0,0,0.30)`
  (dark) / `rgba(15,23,42,0.05)` (light) — it must adapt if tiles ever render in light.
- **CI gate:** extend `check:restraint` with a hex-literal ban for `src/features/**/*.tsx`
  (allowlist: none) and a palette-class ban (`slate-`, `gray-`, `zinc-`, `amber-`,
  `red-[0-9]`, `text-white`, `bg-black`). Design-system internals (`src/shared/design-system/`)
  may use raw values only inside token definitions.

### 4.2 Typography consolidation

Adopt the design-system 8-token scale as the **only** sizes. Mapping for the 9 stray sizes:

| Found | Token | Size |
|---|---|---|
| `text-[9px]`, `text-[10px]`, `text-[11px]` | `text-label-xs` | 11px — nothing below 11px, ever (readability floor) |
| `text-[12px]`, `text-[13px]` | `text-body-sm` | 13px |
| `text-[14px]`, `text-[15px]` | `text-body-md` | 14px |
| `text-[18px]`, `text-[20px]`, `text-[22px]` | `text-display-md` | 24px (page titles) or `text-body-lg` 16px (section heads) — judged per usage |

- Register the scale in `tailwind.config.ts` `fontSize` so `text-body-sm` etc. are real
  utilities; arbitrary `text-[Xpx]` is then lintable.
- **CI gate:** `check:restraint` fails on `text-\[\d+px\]` in feature code.
- Every numeric readout (counts, SLA seconds, timestamps, FPS, GPU %) gets
  `font-mono tabular-nums` — jitter-free columns are a signature premium detail.

### 4.3 Focus & accessibility repairs

- `ForensicSearchPage` `focus:` → `focus-visible:`; all four raw inputs replaced by
  the design-system `Input` (§5.3 below).
- Standardize the ring recipe everywhere:
  `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface-base)]`
  — extract as a `focusRing` cn-fragment in `src/shared/design-system/focus.ts` so it
  can't drift.
- LivePage gains `<Helmet title="Live" />`... (already present — verify) and every layout
  landmark keeps its `aria-label`.

### 4.4 Theme scoping standard

One mechanism, everywhere: **scoped `data-theme` on the layout root element**. The
document root keeps the user's persisted preference; workspaces that force a theme do so
locally and lose the override the moment you navigate away — no effect cleanup races, no
flicker (this fixed the AdminLayout flicker on 2026-07-08).

- `useRouteTheme` hook: **delete** (now unused).
- Error pages (`NotFoundPage`, `ForbiddenPage`): no override — they follow the user
  preference, which is correct; just verify they render on `bg-surface-base` so dark
  preference doesn't show a white flash.
- Design-system doc §6.4 amended to document scoped-attribute as the standard and the
  hook as removed.

---

## 5. Part II — Structure & components

### 5.1 Minimal sidebar (replaces shadcn Sidebar)

The shadcn Sidebar (+ its `button.tsx`, `input.tsx`, `skeleton.tsx`, `tooltip.tsx`,
`use-mobile.tsx` compat satellites) is replaced by a hand-rolled `AppSidebar` in
`src/shared/design-system/components/AppSidebar.tsx`:

- **Structure:** `<aside>` → header slot (logo + workspace badge) → `<nav>` with grouped
  items → footer slot. ~120 lines total.
- **Collapse:** single `collapsed` boolean in `useWorkspacePrefs` (persisted). Collapsed
  width 56px (icons + tooltip labels via the existing design-system Tooltip), expanded
  232px. Ctrl+B toggles (reuse the existing shortcut binding, now in our code).
- **Visuals:** `bg-surface-raised`, `border-r border-border`, group labels `text-label-xs
  uppercase text-text-muted`, active item = `bg-surface-sunken` + 3px brass left border +
  `layoutId` spring (all as today). Works in both themes automatically because it is
  100% token-driven.
- **Deletions:** `ui/sidebar.tsx`, `ui/button.tsx`, `ui/input.tsx`, `ui/skeleton.tsx`,
  `use-mobile.tsx` (keep `ui/tooltip.tsx` only if the design-system Tooltip doesn't
  already cover it — it does; delete). AdminLayout and (new) AnalyticsLayout consume
  `AppSidebar`; the two sidebars become one component with different nav configs.
- **Acceptance:** AdminLayout tests pass unchanged (nav landmark, active-token assertions);
  bundle drops by the shadcn sidebar's weight; `pnpm why @radix-ui/react-tooltip` etc.
  show no orphan deps.

### 5.2 Alert card unification

Merge into **one** `AlertCard` (in `features/live/components/`), superseding both:

- Take `AlarmCard`'s feature set: SLA countdown bar, similar-alerts collapsible,
  Bookmark/Export actions, design-system `Button`s.
- Take `AlertCard`'s token discipline + its `isNew` insert-flash.
- Props: `alert, cameraName, similarAlerts?, isSelected?, isNew?, onAcknowledge?,
  onResolve?, onBookmark?, onExport?` — all optional handlers hide their button.
- Severity vocabulary (border-l-4 + severity text + SLA bar colors) uses `--severity-*`
  and `--surface-chip` tokens only.
- Delete the loser file; migrate `AlertSidebar`/tests; the two test files merge into one.

### 5.3 Raw-element eradication

- `ForensicSearchPage`: 4 raw inputs → `Input` (text) and `Input type="datetime-local"`;
  submit button → `Button`.
- `AnalyticsDashboardPage` quick links → `Button variant="ghost" asChild` around `Link`
  (add `asChild` support to Button if absent — pattern already used by shadcn ecosystem).
- Rule going forward (design-system doc amendment): raw `<button>`/`<input>` in feature
  code requires a code-review justification comment; expected count is zero.

### 5.4 Camera tree & tile redesign (operator console)

The tree sidebar and the tile are doing two jobs badly; split them:

- **`CameraRow`** (new, for the tree): 28px compact row — status dot (8px, pulse when
  alarming), name (truncate), tier chip (`--surface-chip`), optional REC dot. No
  snapshot. Rows are what Linear/Datadog trees look like; snapshots belong in the grid.
- **`CameraTile`** (existing, for grid contexts): keeps snapshot card form, fully
  tokenized per §4.1, used by the paginated grid page and any future multi-up wall.
- **CameraTree** renders `CameraRow`s in the hierarchy (Site→Building→Floor→Zone),
  keeps dnd-kit reorder, search, Virtuoso >200. The 12-tile paginated grid moves out of
  the tree into the focused-panel's "grid layout" mode (GridLayoutSelector already
  exists — wire it to swap FocusedCamera ↔ tile grid).
- Empty tree state: EmptyState with "Add cameras" CTA (deep-link `/admin/cameras`,
  role-gated via `hasPermission`).

### 5.5 App shell unification

Today: 5 shells (Admin, Analytics, Live, Forensic standalone, errors bare). Target: **one
`WorkspaceShell` pattern** with per-workspace config — sidebar nav config, forced theme
(or none), top-bar content. Forensic joins Analytics's shell (it's already linked from
its nav). Error pages get a minimal centered shell with the logo. This is structural
consistency users feel without naming it.

---

## 6. Part III — UI-state doctrine

Binding matrix — every route must implement all five columns before its plan task is
checkable. Skeleton-first: content areas never render spinners (LoadingThreeDotsJumping
is for full-page boot only).

| Route | Loading | Empty | Error | Offline/degraded | Permission-denied |
|---|---|---|---|---|---|
| /live | Skeleton tree + tile shimmer | EmptyState "No cameras" + admin CTA | per-panel error card w/ Retry | OfflineReconnectBanner (exists) + stale-data badge on alert list | RoleGuard (exists) |
| /live FocusedCamera | shimmer | "Select a camera" | **"Stream unavailable" card + Retry + fall back to snapshot** (new) | reconnect w/ backoff indicator | — |
| /analytics | SkeletonChart/KpiCard (exist) | "No data yet" w/ date-range hint | **render `kpiError` — inline error card + Retry** (new) | last-updated timestamp turns amber when >60s stale | RoleGuard |
| /admin/* | SkeletonTableRow (exists) | EmptyState (exists ✓) | toast + inline (exists ✓) | — | RoleGuard |
| /forensic | "Searching…" (exists ✓) | exists ✓ | 501 banner (exists ✓) | — | RoleGuard |

Additional doctrine:
- **Every mutation** gets optimistic UI or a pending state on its trigger button
  (`Button loading` prop — add if absent), plus `vmsToast.error` with a *actionable*
  message (what failed + what to do), never raw error strings from the API.
- **Timestamps:** all "Xm ago" strings re-render on a shared 30s interval hook
  (`useNow(30_000)`) — today they freeze at mount. Absolute time on hover (`title`).
- **Numbers:** counts >999 formatted `1.2k` via one shared `formatCount`; durations via
  one `formatDuration`. No ad-hoc `Math.floor` chains in components.

---

## 7. Part IV — Premium-feel details

Mostly small; collectively they are the "feel". All are token/motion-preset driven.

1. **Page transitions** — already added (150ms fade in Admin/Analytics). Extend the same
   recipe to Forensic; never on /live (operators need zero latency).
2. **Command palette completeness** — every nav destination, every camera, zone, person,
   plus actions ("Acknowledge all visible", "Toggle theme", "Export audit"). Recents
   already persist. Add `?`-style hint chip in TopBar (`⌘K`) in both themes.
3. **Login as brand moment** — the one screen allowed >1 brass usage: logo glow (exists),
   brass primary CTA, subtle animated grid/scanline background at <3% opacity, product
   name in `font-display`. First impressions carry SaaS perception disproportionately.
4. **Charts** — ECharts theme (exists) audited against tokens: gridlines `--border-default`,
   axis labels `--text-muted`, series palette from a new `--chart-1..6` token ramp
   (brass reserved for the single "primary" series), tooltips on `--surface-card` with
   `--shadow-3`.
5. **Toasts** — severity left-borders (done 2026-07-08); cap concurrent toasts at 3;
   errors are `important` (exists).
6. **Density switch (defer-able)** — comfortable/compact table row-height toggle in
   workspace prefs; DataTable already has row-height var (`--table-row-h`) so cost is low.
7. **Scrollbars** — thin themed scrollbars (`scrollbar-width: thin` + WebKit styling on
   `--surface-*`); default OS scrollbars in a dark console read as unfinished.
8. **Favicon/title discipline** — every route sets a title (Helmet audit); favicon
   matches the brass logo mark.
9. **Reduced motion** — every new animation continues to gate on `useReducedMotion()`
   (pattern established in 4L/4M).

---

## 8. Part V — New backend endpoints (contracts)

All endpoints: JWT-authenticated, role-gated per §7.1 of CLAUDE.md, Pydantic schemas in
`vms/api/schemas.py`, one positive + one negative test each. Analytics aggregates come
from PostgreSQL rollups per the recording/analytics spec direction — **no per-frame or
per-request table scans of `tracking_events`** (perf §0.6); use indexed aggregate queries
with a 60s cache.

### 8.1 `GET /api/persons/{person_id}` — unblock PersonProfilePage (404 today)
Response: `{ person_id, full_name, role, created_at, embedding_count, last_seen_at,
last_seen_camera_id, thumbnail_url | null }`. 404 if purged/absent. Roles: manager+.

### 8.2 `GET /api/analytics/kpi` — unblock dashboard KPIs (404 today)
Query: `from`, `to` (default: last 24h). Response:
`{ head_count_peak, head_count_peak_at, avg_dwell_minutes, unknown_person_events,
camera_uptime_pct, open_alerts, alerts_by_severity: {CRITICAL: n, ...} }`.
`camera_uptime_pct` computed from camera status transition history (new lightweight
`camera_status_events` table — status, camera_id, at — written by the existing health
scheduler job; **not** from `is_active`). Roles: manager+.

### 8.3 `GET /api/analytics/head-count` — unblock HeadCountChart (404 today)
Query: `days` (1–90) or `from/to`, `bucket` (`hour`|`day`, default hour). Response:
`{ series: [{ ts, plant_total, by_zone: {zone_id: n} }] }` from the analytics rollup
tables. Roles: manager+.

### 8.4 `GET /api/system/metrics` — kill the fake GPU gauge
Response: `{ gpu: { util_pct, mem_used_mb, mem_total_mb }, cpu_pct, disk: { used_gb,
total_gb }, inference_fps, ingest_lag_ms, ts }`. Source: pynvml + psutil sampled by the
**scheduler** (invariant: scheduler owns recurring work) into Redis every 5s; endpoint
reads Redis — never samples inline. Also published on the existing WebSocket as
`system_metrics` event so TopBar/SystemStatusStrip update live. Roles: any authenticated.

### 8.5 `POST /api/forensic/export` — unblock ClipExportDialog (404 today)
Body: `{ camera_id, from_ts, to_ts, reason }` (reason audited). Until the recording
backend (Phase 3 spec) lands, implementation = frame-sequence export from stored
snapshots/thumbnails or **honest 202 + "queued"** with a `GET /api/forensic/export/{job_id}`
status endpoint; the dialog shows job state instead of silently 404ing. Audit event
`CLIP_EXPORT_REQUESTED`. Roles: guard+ (camera-scoped permission check).

### 8.6 `/api/users` CRUD — unblock AdminUsersPage ("Coming Soon" today)
`GET /api/users`, `POST /api/users`, `PATCH /api/users/{id}` (role, active,
camera-permissions), `POST /api/users/{id}/reset-password`, `DELETE /api/users/{id}`
(soft-deactivate, never hard-delete — audit trail). Admin only; self-demotion and
last-admin-deactivation rejected (edge cases §10). Every mutation writes an audit event.

### 8.7 `/api/bookmarks` — persist live bookmarks
`GET /api/bookmarks?camera_id=`, `POST /api/bookmarks` `{ camera_id, ts, alert_id?,
note? }`, `DELETE /api/bookmarks/{id}`. Per-user rows (`user_id` from JWT). New table +
Alembic migration (+ downgrade). Wires the dead CameraTile/AlarmCard Bookmark buttons.

### 8.8 Explicitly deferred
- HLS live/playback endpoints → recording spec (FocusedCamera keeps MJPEG; remove or
  feature-flag the HLS URL construction so it stops constructing a 404 URL).
- PTZ control → needs ONVIF spec; the FAB button stays disabled with tooltip
  "PTZ available for FULL-tier cameras — coming with camera-control rollout".
- `/api/persons/search` vs `/api/persons?q=` redundancy: frontend standardizes on
  `?q=`; `search` route deprecated in a later cleanup (not removed in this spec).

## 9. Part VI — Wire the orphaned endpoints (data already exists)

| Endpoint | UI destination |
|---|---|
| `GET /api/anomaly-detectors/health` | AdminDashboardPage: detector health card (per-detector status pill; degraded → warning toast on load) |
| `GET /api/maintenance/calendar` | MaintenanceCalendarPage: actual month-grid calendar fed by expansion endpoint (today it only lists windows) |
| `GET /api/sites/readiness-report.pdf` | AdminCamerasPage header: "Readiness report" download Button (admin) |
| `GET /api/forensic/clips/{global_track_id}` | PersonProfilePage: "Recent clips" strip; AlarmCard "Export" precursor view |
| `POST /api/cameras/{id}/recalibrate-required` | CameraDetailPage → HardwareTab: "Flag for recalibration" action w/ confirm |
| `POST /api/persons/{id}/embeddings` | EnrolmentWizard final step actually uploads captured embeddings (verify current wiring; audit says it never calls) |

---

## 10. Edge-case catalog (binding on all Parts)

1. **Zero-data**: 0 cameras, 0 alerts, 0 persons, 0 zones — every list/tree/chart shows
   its designed EmptyState; charts render an empty-axes frame, never `NaN` or a blank div.
2. **Scale**: 500 cameras (Virtuoso threshold verified), 10k alerts (list virtualized +
   server-side pagination — confirm `/api/alerts` `limit/offset` used everywhere),
   200-char camera/person names (truncate + title), zones with identical names
   (disambiguate with floor/building in labels).
3. **Time**: client clock skew (compute "ago" against server `ts` deltas where the
   payload provides one), maintenance windows crossing midnight/DST rendered correctly
   in the calendar, UTC-naive DB timestamps always localized at the edge (one
   `formatTs` util; components never call `new Date(iso)` directly).
4. **Network**: slow (skeletons hold, no layout shift when data lands — reserve
   dimensions), flapping WebSocket (exponential backoff; banner shows attempt count),
   401 mid-session (single redirect to login with return-path, no toast storm),
   403 on a camera-scoped resource (per-panel "No access" card, not a route-level boot).
5. **Auth/roles**: last-admin protection (§8.6), self-role-change rejection, guard user
   sees zero admin nav entries (not disabled ones — hidden, per `hasPermission`).
6. **GDPR**: purged person visited via stale link → PersonProfilePage designed 404 state
   ("This person was removed"); no thumbnail ghosting from cache.
7. **Concurrency**: two operators acknowledge the same alert → second PATCH gets 409 or
   idempotent 200; UI reconciles silently from the WebSocket event, never shows a scary
   error for a benign race.
8. **Reduced transparency/motion**: glass surfaces and all animations degrade (4L
   patterns), including new Part IV items.

---

## 11. Non-goals

- No visual redesign of information architecture (routes/nav structure stay).
- No new charting library, state library, or CSS framework.
- No dark-mode support for admin/analytics (light-forced) beyond what exists — the
  toggle governs non-forced surfaces only.
- No i18n in this spec (worth a future spec; keep strings unconcatenated where cheap).
- No mobile layout work (min supported width stays per frontend spec).

---

## 12. Acceptance criteria & CI gates

1. `check:restraint` extended: hex-literal ban, palette-class ban, `text-[Xpx]` ban in
   `src/features/`; CI red until violations = 0.
2. `grep -r "slate-\|#0a0e1a\|#1a2234\|#232d42" src/features/` → empty.
3. One alert card component; one sidebar component; shadcn sidebar + satellites deleted;
   `useRouteTheme` deleted.
4. UI-state matrix (§6) — a test per cell for the new cells (stream-error, kpi-error,
   camera-empty).
5. All §8 endpoints: implemented + 1 positive + 1 negative test each + frontend consumer
   live; the three 404 calls from audit List 1 are gone (implemented or removed).
6. All §9 orphans wired or explicitly re-deferred with a plan checkbox.
7. Frontend gate green: `pnpm lint && pnpm typecheck && pnpm test:run`; coverage floors
   hold (shared ≥80%, features ≥70%). Backend gate: `black`, `ruff`, `mypy --strict`,
   `pytest` green; new tables have migrations with tested downgrades.
8. Perf budgets from frontend spec §17 unchanged and still met (bundle should *shrink*
   from the shadcn deletion).

---

## 13. Resolved decisions (2026-07-08, user-approved)

1. **`camera_status_events` table ships** (§8.2). Append-only `(camera_id, status, at)`
   rows written by the existing health scheduler job on every status *transition* (not
   every check). Uptime = aggregate over the window. Alembic migration with tested
   downgrade.
2. **Clip export ships as 202-queued** (§8.5). `POST /api/forensic/export` creates an
   `export_jobs` row (`QUEUED`), returns 202 + `job_id`; `GET /api/forensic/export/{job_id}`
   reports state. The recording backend (Phase 3 spec) later adds the worker that
   transitions jobs to `COMPLETE`; until then jobs remain honestly `QUEUED` and the
   dialog shows "Export queued — processing begins when the recording service deploys."
3. **Chart token ramp fixed.** Brass is `--chart-1` (the single primary series); 2–6 are
   distinct from all severity hues, tuned per theme for contrast on their surfaces:

   | Token | Light | Dark |
   |---|---|---|
   | `--chart-1` | `var(--brand-accent)` `#a8752c` | `var(--brand-accent)` `#c8912f` |
   | `--chart-2` | `#2563eb` (blue) | `#60a5fa` |
   | `--chart-3` | `#0d9488` (teal) | `#2dd4bf` |
   | `--chart-4` | `#7c3aed` (violet) | `#a78bfa` |
   | `--chart-5` | `#db2777` (magenta) | `#f472b6` |
   | `--chart-6` | `#0891b2` (cyan) | `#22d3ee` |

   Severity hues (red/orange/amber/lime) never appear as generic series colors.

---

## 14. Phasing → plan files (derived from this spec)

| Plan | Contents | Depends on |
|---|---|---|
| **4N — Design language & structure** | Parts I + II (tokens, typography, focus, theme standard, AppSidebar, alert-card merge, CameraRow/tile split, shell unification) + §12 CI gates | — |
| **4O — UI states & premium details** | Parts III + IV (state matrix, useNow/formatters, transitions, palette completeness, login moment, chart theming, scrollbars) | 4N (tokens) |
| **4P — Data completeness (backend + wiring)** | Parts V + VI (§8 endpoints w/ migrations, §9 orphan wiring, delete dead FAB stubs or wire them) | none for backend; frontend wiring after 4N |

Each plan follows the §16 CLAUDE.md conventions (TDD tasks, checkboxes, one plan per
phase, reviewed before implementation). Phase 5 security remains the GA gate and is not
displaced by this work.

---

**End of specification.**
