# Phase 4I — Design System Refresh: Implementation Notes

**Companion to:** `docs/superpowers/plans/2026-07-06-vms-phase4i-design-refresh.md`
**Design system:** `docs/frontend/2026-06-24-vms-design-system.md`
**Frontend spec:** `docs/frontend/2026-05-01-vms-frontend-spec.md`
**Status:** NOT STARTED — notes written ahead of implementation
**Date:** 2026-07-07 (IST)

> This file is the *how it should look and feel* companion to the Phase 4I plan. The plan
> says what to do task-by-task; this file records the exact visual intent, class strings,
> and "done looks like" targets so the implementation reads as Linear/Vercel/Retool-grade
> rather than a generic admin template. Read §C (signature decisions) and §E (gap analysis)
> before touching a single file — they are the design thesis. Everything else is execution.

---

## The thesis in one sentence

We are building a **control-room instrument**, not a dashboard. The visual language is
quiet structure (uppercase micro-labels, tabular numbers, mono data register), one loud
brand mark (crimson), and one loud alarm color (red) that never touch each other. The
discipline of *what stays quiet* is what makes the loud things read as signal.

---

## A. Per-task design decisions

### Task 1 — `index.css`: duration vars + light-theme interactive tokens

**Current state (confirmed in code, `frontend/src/index.css`):**
```
line 41  --focus-ring: #2b6cb0;        ← BLUE
line 42  --interactive-hover: #1a4480; ← BLUE
line 62  --selected-row: #eef6ff;      ← BLUE tint
```

**Target (light theme `:root` block):**
```css
--focus-ring: #1e293b;          /* action-700 charcoal — clean dark ring on white */
--interactive-hover: #0f172a;   /* action-800 */
--interactive-active: #020617;  /* action-900 */
--selected-row: #f1f5f9;        /* neutral slate-100 — NO blue tint */
--brand-accent: #c0392b;        /* NEW — crimson; consumed only by nav bar + logo */

/* motion */
--duration-fast: 100ms;    /* hover/elevation feedback */
--duration-base: 150ms;    /* default transitions, focus */
--duration-slow: 250ms;    /* modal/drawer enter */
```

**Dark theme (`[data-theme="dark"]`) — do NOT charcoal the ring here.** On a dark surface
`#1e293b` is nearly invisible. Keep the dark focus ring light:
```css
--focus-ring: #94a3b8;    /* slate-400 — visible on dark */
--selected-row: #1e293b;  /* neutral raised, not blue */
```
The `--brand-accent: #c0392b` value is identical in both themes — crimson reads as a warm
red on dark and holds its brand meaning.

**Visual intent:** the focus ring stops looking like a hyperlink and starts looking like a
deliberate UI affordance. Selected rows go neutral so the *only* saturated color in a data
table is a status badge — the eye goes straight to state, not to chrome.

**Done looks like:** tab through the login form on a white card — the ring is a crisp
dark 2px outline with 2px offset, not a blue glow. Select a table row — it goes light-grey,
not blue.

---

### Task 2 — `tailwind.config.ts`: brand scale → crimson, add action scale, durations

**Replace** the blue `brand` scale with crimson, centered on 500 = `#c0392b`:
```ts
brand: {
  50:  '#fdf3f2', 100: '#fbe3e0', 200: '#f5c2bc', 300: '#eb9a90',
  400: '#dc6a5c', 500: '#c0392b', 600: '#a52f23', 700: '#87271d',
  800: '#6d2019', 900: '#5a1c17',
},
```
**Add** the action (interactive) scale — charcoal, the workhorse for buttons/rings:
```ts
action: {
  50:  '#f8fafc', 100: '#f1f5f9', 200: '#e2e8f0', 300: '#cbd5e1',
  400: '#94a3b8', 500: '#64748b', 600: '#475569', 700: '#1e293b',
  800: '#0f172a', 900: '#020617',
},
```
**Add** transitionDuration referencing the CSS vars so JS-land and CSS-land agree:
```ts
transitionDuration: {
  fast: 'var(--duration-fast)',
  base: 'var(--duration-base)',
  slow: 'var(--duration-slow)',
},
```

**Visual intent:** `brand-*` now *means* crimson. Any pre-existing `bg-brand-500` in the
codebase instantly becomes wrong-by-color (it will render crimson where blue buttons used
to be) — this is intentional and forces Task 3/5/6 to be found and fixed. Grep for
`brand-` after this task; every hit is a decision.

**Done looks like:** `bg-action-700` exists and renders `#1e293b`; `text-brand-500`
renders crimson.

---

### Task 3 — `Button.tsx`: primary → charcoal

**Current:** primary variant uses `bg-brand-500` (was blue, now would render crimson — wrong).

**Target primary variant classes:**
```
bg-action-700 text-white hover:bg-action-800 active:bg-action-900
focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2
focus-visible:outline-[color:var(--focus-ring)]
disabled:bg-action-300 disabled:text-white/70
transition-colors duration-base
```
Secondary/ghost/destructive unchanged EXCEPT destructive stays `bg-[#dc2626]`
(alarm red — see §C.3; destructive delete is the one legitimate non-badge use of alarm red,
because a purge *is* a severity action).

**Visual intent:** primary buttons become confident, neutral, expensive-looking charcoal.
The page's saturated color budget is spent entirely on the crimson logo/nav-bar and on
status. A wall of blue buttons is the #1 tell of a generic admin template; charcoal reads
as Linear/Vercel.

**Done looks like:** the "Add Camera" / "Save" buttons are near-black, darken on hover, and
show a matching dark focus ring. No blue, no crimson.

---

### Task 4 — `LoginPage.tsx`: 3px crimson top-border on card

**Target:** the auth card gets a crimson top edge — the single brand touch on the page.
```
border-t-[3px] border-t-brand-500
```
Card body otherwise neutral (`bg-surface-raised rounded-lg shadow-2 border border-border`).
The wordmark above the form uses `text-brand-500` for the "VMS" mark only.

**Visual intent:** first impression = "this is a specific product." The crimson hairline is
a signature, not decoration. Everything else on the login page is quiet.

**ASCII anatomy:**
```
┌━━━━━━━━━━━━━━━━━━━━┐  <- 3px crimson (#c0392b)
|                    |
|     [VMS] logo     |  <- wordmark crimson, rest neutral
|                    |
|  Email  [_______]  |
|  Pass   [_______]  |
|                    |
|  [   Sign in   ]   |  <- charcoal action-700 button
+--------------------+
```

**Done looks like:** the only saturated pixels on the login screen are the 3px top rule and
the wordmark. Button is charcoal. Focus rings dark.

---

### Task 5 — `AdminLayout.tsx`: crimson 3px left-bar active indicator

**Current:** active nav item = `bg-brand-500/15 text-brand-300` (a filled blue pill — now
would be a crimson pill, still wrong; we do NOT want a fill).

**Target active item (dark sidebar, `data-theme="dark"`):**
```
relative text-white
before:absolute before:left-0 before:top-1 before:bottom-1 before:w-[3px]
before:rounded-r before:bg-brand-500
```
**Inactive item:**
```
text-white/60 hover:text-white hover:bg-white/5 transition-colors duration-fast
```
No background fill on active — the crimson left-bar + full-white text *is* the active state.

**Sidebar section labels (the operational vocabulary — see §C.1):**
```
text-[10px] font-semibold uppercase tracking-[0.10em] text-white/30 px-3 mt-5 mb-1
```
Label groups, in order: **SURVEILLANCE** (Dashboard, Cameras, Live) · **IDENTITY** (Persons,
Zones) · **SCHEDULING** (Maintenance, Alert Routing) · **SYSTEM** (Anomaly Detectors, Audit
Log, Analytics).

**Visual intent:** the 3px crimson bar is the *only* place brand color appears in the app
chrome besides the logo. It's a wayfinding accent, not a button. On the dark sidebar,
`brand-500` (`#c0392b`) reads as a warm, confident red — it holds brand meaning without a
fill that would compete with alarm red elsewhere.

**Done looks like:** the active route has a crisp 3px crimson vertical bar flush to the
sidebar's left edge and bright-white label; inactive items are 60% white and lift to a
faint white-5% wash on hover. Section labels are near-invisible until you look for them.

---

### Task 6 — `AnalyticsLayout.tsx`: crimson 3px left-bar (light sidebar)

Same pattern, light-sidebar tokens:
**Active:**
```
relative text-text-primary font-medium
before:absolute before:left-0 before:top-1 before:bottom-1 before:w-[3px]
before:rounded-r before:bg-brand-500
```
**Inactive:** `text-text-secondary hover:text-text-primary hover:bg-surface-sunken`.
Section labels: `text-[10px] font-semibold uppercase tracking-[0.10em] text-text-muted px-3 mt-5 mb-1`.

**Visual intent:** identical wayfinding grammar across both layouts. A user who learns the
admin sidebar reads the analytics sidebar instantly. The crimson bar is the constant.

**Done looks like:** the active-indicator treatment is pixel-identical between admin (dark)
and analytics (light) except for text/hover tokens.

---

### Task 7 — `PageHeader` shared component

See full spec in §D.1. **Visual intent:** every page opens with the same three-part header
(title / optional subtitle / right-aligned actions) so the app has one skyline. The title
is the largest type on the page at `text-[22px] font-bold` — it establishes "you are here."

**Done looks like:** every page's top section is a consistent header; no page hand-rolls its
own `<h1>`.

---

### Task 8 — `EmptyState`: promote to shared

Move from `src/features/admin/components/EmptyState.tsx` to
`src/shared/design-system/components/EmptyState.tsx`. Update all imports. See §D.2 for the
props/copy spec. **Visual intent:** empty states are operator-facing microcopy, not "No
data." Promoting it makes the *voice* reusable, not just the box.

**Done looks like:** one `EmptyState` import path; feature-scoped copy passed as props; the
old feature-scoped file deleted and no dangling imports.

---

### Task 9 — `CameraStatusBadge`: 12-state component

Full state table in §D.3. **Visual intent:** camera state is the single most-scanned datum
in a VMS. A 4-state inline badge under-communicates; operators need to distinguish
"streaming" from "recording" from "reconnecting" from "auth failed" at a glance. Twelve
states, each with a fixed color + icon + pulse rule, turn the camera grid into an instrument
panel.

**Done looks like:** every camera row/tile uses `<CameraStatusBadge status={...} />`; no
inline status ternaries remain in camera views.

---

### Task 10 — `Skeleton` + replace 10 loading patterns

Full spec §D.4. Replace all 10 plain `Loading...` text instances (confirmed locations:
`AdminPersonsPage`, `AlertRoutingPage`, `AnomalyDetectorsPage`, `AuditLogViewerPage`,
`HardwareTab`, `OverridesTab`, `CameraDetailPage` x2, `MaintenanceCalendarPage`,
`ZoneEditorPage`) with shape-matched skeletons. **Visual intent:** a skeleton that mirrors
the eventual layout (table rows, card grid) makes load feel instant and intentional; a
"Loading..." string makes it feel broken. Never a centered spinner on a full page except the
initial app boot.

**Done looks like:** grep for `Loading...` returns zero hits in page components; each former
site shows a layout-shaped shimmer.

---

### Task 11 — Card hover elevation on dashboard cards

**Target for every interactive KPI/summary card:**
```
shadow-1 transition-shadow duration-fast hover:shadow-2
```
Do NOT change the border on hover (see §F). **Visual intent:** the shadow step (1→2)
communicates "this is interactive/liftable" with physical depth, the Linear/Retool
signature. A border-color flicker reads as a bug; a shadow lift reads as craft.

**Done looks like:** hovering a dashboard KPI card raises it a step (softer, larger shadow)
in 100ms with no layout shift and no border change.

---

### Task 12 — Quality gate

`pnpm lint && pnpm typecheck && pnpm test:run` clean. Coverage: `src/shared/` >= 80%,
`src/features/` >= 70%. New shared components (`PageHeader`, `EmptyState`,
`CameraStatusBadge`, `Skeleton`) each ship with a test. Add a **visual-regression guard
grep** to the PR checklist: `grep -rn "bg-brand-500" src` should only match the login card
top-border and the two sidebar active bars — any other hit is a Task-3 miss.

**Done looks like:** all gates green; the brand-500 grep is clean of button usage.

---

## B. Per-page SaaS polish checklist

Each page below lists the concrete items that move it from "functional" to "SaaS-grade."
The shared grammar applies everywhere:

- **Page padding** `p-6` (24px) · **card padding** `p-4` (16px) · **card gap** `gap-4` · **section margin** `mb-8` — 8pt grid, zero exceptions.
- **Table header** `text-[11px] font-semibold uppercase tracking-[0.06em] text-text-secondary bg-surface-sunken h-9`.
- **Status badge** `text-[12px] font-medium leading-none px-2 py-1 rounded-full` — color `/15` bg + full-opacity text.
- **Mono data register** `font-mono text-[13px]` for every ID, hash, timestamp, FPS, camera ID.
- **Tabular numbers** on every numeric cell/counter (see §F tabular-nums gotcha).

### Admin Dashboard
- **Typography:** `PageHeader` title 22px bold "Dashboard"; subtitle "System overview · live". KPI numbers are the hero: `text-[28px] font-bold tabular-nums text-text-primary`; KPI labels `text-[11px] font-semibold uppercase tracking-wider text-text-muted mt-1`.
- **Cards:** KPI grid `grid gap-4`, each card `p-4 rounded-lg border border-border bg-surface-raised shadow-1 hover:shadow-2 transition-shadow duration-fast`. Trend delta small, right-aligned, green/red by sign (delta green = `#16a34a`, negative = `#dc2626` — the one numeric use of alarm red is acceptable for a genuinely bad trend).
- **Empty state:** if no cameras yet → `EmptyState` "No cameras configured · Add your first camera to begin monitoring" + [Add Camera].
- **Loading:** `SkeletonKpiGrid` (4 shimmer cards) then `SkeletonTable` for the recent-alerts list.
- **Page-specific:** live-count KPIs use tabular-nums so digits don't jitter as they tick.

### Camera List
- **Typography:** title "Cameras", subtitle = live count e.g. "48 of 52 online" (`font-mono tabular-nums` on the numbers).
- **Table:** uppercase header row; columns Camera ID (`font-mono text-[13px]`), Name, Zone, FPS (`font-mono tabular-nums`, right-aligned), Status (`CameraStatusBadge`). Selected row uses `--selected-row` neutral grey.
- **Empty state:** "No cameras assigned · Assign cameras to begin monitoring" + [Add Camera].
- **Loading:** `SkeletonTable rows={8}` matching the real column widths.
- **Page-specific:** the status column is the focal point — it is the only saturated color in the table (badges), everything else is neutral text + mono IDs.

### Person List
- **Typography:** title "Persons", subtitle count.
- **Table:** columns Thumbnail (rounded 32px), Name, Person ID (`font-mono text-[13px]`), Enrolled embeddings (tabular-nums), Last seen (`font-mono` timestamp), Zone. GDPR delete is a `destructive` button → alarm red (legitimate severity use).
- **Empty state:** "No persons enrolled · Enroll a person to enable identity matching" + [Enroll Person].
- **Loading:** `SkeletonTable` with a leading circle column for the thumbnail.
- **Page-specific:** biometric-sensitive — never render embedding vectors; the "embeddings" column is a count only.

### Analytics Dashboard
- **Typography:** title "Analytics"; section labels above each chart group `text-[11px] font-semibold uppercase tracking-[0.06em] text-text-secondary`.
- **Cards/charts:** chart cards get the same `shadow-1 hover:shadow-2`. Axis tick labels and legend counts in `tabular-nums`. KPI roll-ups reuse the dashboard KPI anatomy.
- **Empty state:** "No data for this range · Adjust the date range or wait for events to accumulate."
- **Loading:** `SkeletonChart` (a shimmer block sized to the chart) — never a spinner over a chart.
- **Page-specific:** analytics runs on the light sidebar layout; the crimson left-bar indicator must match admin exactly.

### Login
- Covered by Task 4. Polish beyond that: error toast uses alarm styling (auth failure = severity-legitimate red text), inputs get the dark focus ring, "Sign in" button charcoal, card has the 3px crimson top rule and neutral shadow-2. No blue anywhere.

### Guard Live View (full dark)
- **Typography:** camera tile captions `font-mono text-[13px] text-white/70` (camera ID + FPS). Alarm banner title `text-[13px] font-semibold uppercase tracking-wide`.
- **Cards/tiles:** video tiles have no hover-shadow (they're not liftable); selected tile gets `ring-2 ring-white/40` — no crimson here. An *alarming* tile (active anomaly) gets `border-2 border-[#dc2626]` + the pulse animation (see §D.3 pulse rule) — this is the flagship legitimate alarm-red use.
- **Empty state:** "No cameras in this view · Select cameras from the sidebar to build a live layout."
- **Loading:** per-tile `SkeletonTile` (dark shimmer) while the stream negotiates.
- **Page-specific:** this is the one screen where alarm red is loud and constant-motion (pulse). Because red is banished everywhere else, an alarming tile here is unmissable — that exclusivity is a safety feature, not just aesthetics.

---

## C. Signature design decisions

These five choices, taken together, are the app's voice. If a future change erodes one of
them, the app slides back toward "generic dashboard." Guard them.

### C.1 Sidebar operational vocabulary — SURVEILLANCE / IDENTITY / SCHEDULING / SYSTEM
Section labels use the domain's language, not SaaS-generic groupings. **Not** "MONITORING /
PEOPLE / OPERATIONS / SETTINGS" — those could belong to any CRM. "SURVEILLANCE / IDENTITY /
SCHEDULING / SYSTEM" tells the operator this tool was built for a control room. Rendered
extremely quiet (`text-white/30`, 10px, `tracking-[0.10em]`) so the vocabulary registers
subconsciously as *purpose-built* without shouting.

### C.2 Mono data register
Every ID, hash, timestamp, FPS counter, and camera ID renders in `font-mono text-[13px]`
(JetBrains Mono). This creates two visual registers: **interface** (sans, for labels/actions)
and **data** (mono, for machine values). The instant a user sees a mono string they know
"this is a real value from the system," not UI copy. This single split does more for the
"serious instrument" feel than any color choice.

### C.3 Crimson-accent-only brand
Crimson (`#c0392b`) appears in exactly **two** places: the logo/wordmark and the 3px nav
active left-bar. Never on a button, focus ring, selected row, chart series, or background.
The scarcity is the point — one restrained brand mark reads as confident; brand color
sprayed across buttons reads as a template.

### C.4 Tabular numbers on KPIs and counters
Every number that can change (live counts, FPS, KPI heroes, analytics ticks) uses
tabular-nums so digits occupy fixed cells and don't jitter/reflow as they update. A live
head-count that shifts horizontally as it ticks looks amateur; a rock-steady counter looks
engineered.

### C.5 The 12-state camera status vocabulary
Cameras aren't "up/down." Twelve states (§D.3) each with a fixed color, icon, and pulse rule
turn a status column into a diagnostic instrument — an operator distinguishes "reconnecting"
(recoverable, amber, pulse) from "auth failed" (needs action, red, static) without reading
text.

---

## D. Component specs — 4 new shared components

All live in `src/shared/design-system/components/`. Each ships with a `.test.tsx` and is
exported from the design-system barrel.

### D.1 `PageHeader`

**Props:**
```ts
interface PageHeaderProps {
  title: string;
  subtitle?: string | React.ReactNode;   // often a live count -> render mono/tabular
  actions?: React.ReactNode;              // right-aligned buttons
  breadcrumbs?: { label: string; to?: string }[];
}
```
**Anatomy:**
```
+-----------------------------------------------------------+
| Home / Cameras                    (breadcrumbs, 11px)     |
| Cameras                    [Add Camera] [Export]          |
| 48 of 52 online  (subtitle, secondary, mono for numbers)  |
+-----------------------------------------------------------+
```
**Classes:**
- Wrapper: `flex items-start justify-between gap-4 mb-8`
- Title: `text-[22px] font-bold leading-tight text-text-primary`
- Subtitle: `text-[13px] text-text-secondary mt-1` (wrap numbers in `<span className="font-mono tabular-nums">`)
- Breadcrumbs: `text-[11px] text-text-muted mb-1`
- Actions slot: `flex items-center gap-2 shrink-0`

### D.2 `EmptyState`

**Props:**
```ts
interface EmptyStateProps {
  icon?: React.ReactNode;      // lucide icon, 24px, text-text-muted
  title: string;               // "No cameras configured"
  description?: string;        // operator-facing next action
  action?: { label: string; onClick: () => void };
}
```
**Classes:**
- Container: `flex flex-col items-center justify-center text-center py-16 px-6`
- Icon wrap: `mb-3 text-text-muted`
- Title: `text-[15px] font-semibold text-text-primary`
- Description: `text-[13px] text-text-secondary mt-1 max-w-sm`
- Action: `Button variant="primary" size="sm" className="mt-4"`

**Copy per context (write exactly like this):**

| Context | title | description | action |
|---|---|---|---|
| Cameras | No cameras assigned | Assign cameras to begin monitoring | Add Camera |
| Dashboard | No cameras configured | Add your first camera to begin monitoring | Add Camera |
| Persons | No persons enrolled | Enroll a person to enable identity matching | Enroll Person |
| Zones | No zones defined | Draw a zone to group cameras and set rules | New Zone |
| Maintenance | No maintenance windows | Schedule a window to pause detection safely | Schedule Window |
| Anomaly detectors | No detectors enabled | Enable a detector to start anomaly monitoring | Configure Detectors |
| Alert routing | No routes configured | Add a route to deliver alerts to your team | Add Route |
| Audit log | No audit events in range | Adjust the date range to view earlier activity | — |
| Analytics | No data for this range | Adjust the date range or wait for events to accumulate | — |
| Forensic search | No results | Refine your query or widen the time window | — |
| Guard live view | No cameras in this view | Select cameras from the sidebar to build a live layout | — |

**Voice rules:** name the specific object ("cameras", "persons"), name the next action, keep
to one line of description, never "No data available."

### D.3 `CameraStatusBadge` — 12 states

**Props:** `{ status: CameraStatus; showLabel?: boolean }` where `CameraStatus` is a union of
the 12 keys below. Base classes: `inline-flex items-center gap-1.5 text-[12px] font-medium
leading-none px-2 py-1 rounded-full` with `bg-{color}/15 text-{color}`.

| # | status | Label | Color (text + /15 bg) | Icon (lucide) | Pulse |
|---|---|---|---|---|---|
| 1 | `streaming` | Streaming | emerald `#10b981` | Video | no |
| 2 | `recording` | Recording | emerald `#10b981` | Circle (filled) | slow pulse |
| 3 | `online_idle` | Online | slate `#64748b` | Wifi | no |
| 4 | `connecting` | Connecting | sky `#0ea5e9` | Loader | spin |
| 5 | `reconnecting` | Reconnecting | amber `#f59e0b` | RefreshCw | pulse |
| 6 | `degraded` | Degraded | amber `#f59e0b` | AlertTriangle | no |
| 7 | `low_fps` | Low FPS | amber `#f59e0b` | Activity | no |
| 8 | `offline` | Offline | slate `#94a3b8` | WifiOff | no |
| 9 | `auth_failed` | Auth failed | red `#dc2626` | KeyRound | no |
| 10 | `stream_error` | Stream error | red `#dc2626` | AlertOctagon | no |
| 11 | `device_fault` | Device fault | red `#dc2626` | AlertOctagon | pulse |
| 12 | `disabled` | Disabled | slate `#64748b` at 40% opacity | Ban | no |

**Pulse rules:** only three states animate — `recording` (slow 2s pulse = "actively
capturing"), `reconnecting` (pulse = "working on it"), `device_fault` (pulse = "needs
attention now"). Everything else is static; motion is reserved so that a pulsing badge always
means "something is happening." Use `motion-safe:animate-pulse` so `prefers-reduced-motion`
disables it.

**Color grouping intent:** green = healthy/active, amber = attention-but-recoverable, red =
action-required, slate = neutral/inactive. Red here is the alarm tier (§C.3) and its only
in-chrome home.

### D.4 `Skeleton` — base primitive + 4 composites

**Base:**
```tsx
<div
  className="motion-safe:animate-pulse rounded bg-surface-sunken"
  style={{ width, height }}
/>
```
Never uses brand or action color — always neutral `surface-sunken`.

**Composites (same file, named exports):**
- `SkeletonText` — `h-3 rounded` line; prop `lines?: number` renders stacked rows with `gap-2`, last line `w-2/3`.
- `SkeletonTable` — props `{ rows?: number; cols?: number }`; renders the uppercase header row (real, not shimmer) + `rows` shimmer rows matching column widths. Replacement for 8 of the 10 `Loading...` sites.
- `SkeletonKpiGrid` — `grid gap-4` of N (default 4) shimmer cards sized like KPI cards (`h-24`), used on dashboard/analytics.
- `SkeletonTile` — dark-surface square shimmer for Guard live-view video tiles (`aspect-video bg-white/5`).

**Visual intent:** the skeleton mirrors the *shape* of what's arriving, so the transition to
real content is a fill, not a swap. Full-page spinners are banned except initial app boot.

---

## E. The SaaS-feel gap analysis (Phase 4H → Linear-grade)

Concrete, itemized deltas between the current state and the target. Each maps to a Phase 4I task.

1. **Primary button is blue `#2b6cb0` → must be charcoal `#1e293b`.** The single biggest "template" tell. (Task 2/3)
2. **Focus ring is blue `#2b6cb0` → must be charcoal `#1e293b`** (light) / slate on dark. Blue rings read as browser-default links. (Task 1)
3. **Interactive hover/active tokens are blue (`#1a4480` / `#102a4c`) → charcoal `#0f172a` / `#020617`.** (Task 1)
4. **Selected row is blue-tinted `#eef6ff` → neutral `#f1f5f9`.** Saturated selection chrome competes with status badges for attention. (Task 1)
5. **No brand accent token → add `--brand-accent: #c0392b`** and confine it to logo + nav bar. (Task 1/5/6)
6. **Sidebar active state is a filled pill (`bg-brand/15`) → 3px left-bar, no fill.** Filled pills look heavy; a hairline bar is the modern wayfinding idiom. (Task 5/6)
7. **Sidebar has no section labels / generic ones → add quiet operational-vocabulary labels** (SURVEILLANCE/IDENTITY/SCHEDULING/SYSTEM). (Task 5/6)
8. **Tables lack the uppercase micro-header treatment →** apply `text-[11px] uppercase tracking-[0.06em] bg-surface-sunken h-9` everywhere. (per-page, §B)
9. **Numbers are proportional, not tabular → add tabular-nums** on all KPIs/counters/FPS. (per-page, §B + §F gotcha)
10. **IDs/timestamps/hashes render in the body font → mono register** (`font-mono text-[13px]`). (per-page, §B)
11. **10 pages show plain `Loading...` → shape-matched Skeletons.** (Task 10)
12. **Empty states are generic/absent → operator-voice `EmptyState`** with named next action. (Task 8, copy in §D.2)
13. **No page-header consistency → `PageHeader`** gives every page one skyline. (Task 7)
14. **Cards are flat/static → `shadow-1 hover:shadow-2` lift** on interactive cards. (Task 11)
15. **Camera status is 4-state inline → 12-state `CameraStatusBadge`** instrument. (Task 9)
16. **No motion vocabulary → `--duration-fast/base/slow`** tokens so timing is consistent and reduced-motion-aware. (Task 1)

---

## F. What to watch for during implementation (common mistakes)

**1. `brand-500` where `action-700` belongs.** After Task 2, `brand-500` is crimson. Any
leftover `bg-brand-500` on a button will render a crimson button — wrong. After the layout
tasks, run `grep -rn "brand-500" frontend/src`; the ONLY legitimate hits are the login card
top-border (Task 4) and the two sidebar active left-bars (Task 5/6). Every other hit is a
bug. Buttons/rings/toggles use `action-700/800/900`, never `brand-*`.

**2. Alarm red `#dc2626` creeping into non-alarm contexts.** Red is Tier 3 and its power is
its scarcity. Legitimate uses ONLY: `CameraStatusBadge` red states (auth_failed, stream_error,
device_fault), alarm card borders + pulse in Guard view, destructive/GDPR-delete buttons, and
a genuinely negative KPI trend delta. **Never** use red for a primary CTA, a focus ring, a
selected row, a link, or a generic "important" callout. If reaching for red to mean
"emphasis," use charcoal or a badge instead.

**3. Dark-theme sidebar + crimson.** The admin sidebar carries `data-theme="dark"`. The
crimson `brand-500` (`#c0392b`) is intentionally used as the active left-bar here and reads
correctly — a warm red on the dark surface holds brand meaning. **Do not** try to "fix" it
to a lighter tint for contrast; the 3px bar against near-black is exactly the intended look.
What you MUST change on dark is the *focus ring* (`#1e293b` charcoal is invisible on dark →
use slate `#94a3b8`) and *selected-row* (neutral raised, not blue).

**4. Card hover = shadow step, never a border change.** Use
`shadow-1 hover:shadow-2 transition-shadow duration-fast`. A `hover:border-brand`/color-swap
causes a 1px layout reflow and reads as a flicker/bug; a shadow lift reads as physical depth
and is the Linear/Retool signature. Do not add a border transition.

**5. The tabular-nums gotcha.** `tabular-nums` is a Tailwind utility that emits
`font-variant-numeric: tabular-nums` — but it only takes effect if the font actually ships
tabular figures and no conflicting `font-variant-numeric` is set upstream. For hero KPI
numbers, the safest path is the mono register (JetBrains Mono is monospaced → inherently
tabular). If a live counter still jitters after adding the class, the fix is usually to put
the number in `font-mono`, not to hunt for a missing CSS property. Verify in-browser that
ticking counters don't shift horizontally — that's the acceptance check.

**6. Update BOTH themes in Task 1.** `index.css` has both light (`:root`) and dark
(`[data-theme="dark"]`) blocks. The dark block also carries blue tokens
(`--focus-ring: #7eb0ff`, `--selected-row: #0a1c33`, etc.). A common miss is fixing only
`:root` and leaving the dark theme blue, which then shows up on the admin sidebar and Guard
view.

**7. Motion must respect `prefers-reduced-motion`.** All pulses/spins/shimmers use
`motion-safe:` variants so reduced-motion users get static badges and skeletons. This is an
accessibility gate (design-system §13), not optional.
