# Phase 4K — Live View Dark Operator Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use the `frontend-design` skill at the start of each implementation task to get aesthetic guidance for any new component being built. Run `pnpm lint && pnpm typecheck && pnpm test:run` after every task.

**Status: NOT STARTED**

**Goal:** Build the premium dark operator console for `/live`: a three-column workstation (320px camera tree | 1fr focused view | 380px alert sidebar) with a live camera grid, HLS focused view with bounding-box overlay, an alarm sidebar with SLA countdowns and keyboard-driven acknowledge/resolve, a status strip, an offline/reconnect banner, a keyboard shortcut legend, clip export, and floor-plan/fullscreen toggles. This is the operator's primary surface; it must feel calm, dense, and instantly responsive.

**Architecture:** `/live` renders inside a forced-dark theme scope (the route sets a `theme-dark` wrapper so the console is always dark regardless of the global theme toggle). State lives in the existing `liveStore` (Zustand), extended with grid layout, focus, follow, bookmarks, and the live alert list. Live data arrives over one socket.io connection managed by `useLiveAlerts`; camera thumbnails poll via `useCameraSnapshot` (TanStack Query `refetchInterval: 2000`). HLS.js attaches to a `<video>` element on focus change. Bounding boxes render as an absolutely-positioned SVG layer over the video, throttled to 5fps, mapping normalized person coordinates from WS events. Many components already exist (`CameraTile`, `AlertCard`, `AlertSidebar`, `FocusedCamera`, `TopBar`, `BboxOverlay`, `PersonDot`, `DegradedBanner`, `HeadCountBanner`) — this phase reworks them into the dark console and fills the gaps rather than greenfielding.

**Tech Stack:** React 18 + TS, Tailwind 3.4, Zustand 4 (`liveStore`), TanStack Query v5, socket.io-client, HLS.js, Leaflet + react-leaflet (floor plan), Framer Motion (from Phase 4J — banner slide, palette), shadcn primitives (Dialog/Sheet/Select/Collapsible/Switch from Phase 4J), Recharts (none here), Vitest + Testing Library, Playwright (E2E smoke).

**Spec refs:**
- `docs/frontend/2026-05-01-vms-frontend-spec.md` §6 (Live View / TopBar / Cmd+K)
- `docs/frontend/2026-06-24-vms-design-system.md` §6.1 (tokens), §7.6 (collapsible alert group), §9 (motion), §13 (a11y)
- `docs/superpowers/specs/2026-07-06-vms-enterprise-interaction-guidelines.md` §5 (SLA/escalation), §6 (camera health), §7 (live controls, shortcuts), §8 (offline/reconnect), §12 (a11y)

**Dependency:** Phase 4J must be COMPLETE first. Phase 4K TopBar reuses the Cmd+K Command palette (4J Task 4) and the shadcn Sheet/Dialog/Select/Collapsible/Switch primitives (4J Tasks 2–3).

---

## Binding design rules for the dark console

**Dark surfaces (exact literals — these are the console palette, applied inside the `theme-dark` scope):**
- App background: `bg-[#0a0e1a]` (deepest — page/gutter)
- Panel background: `bg-[#111827]` (camera tree, alert sidebar)
- Card/tile background: `bg-[#1a2234]` (camera tile, alarm card)
- Raised/hover: `bg-[#232d42]`
- Hairline border: `border-[#1e293b]`
- Primary text: `text-slate-100`; muted: `text-slate-400`; faint: `text-slate-500`
- Mono data register (IDs, hashes, timestamps, FPS, coords): `font-mono text-[13px] text-slate-300`

**Color separation (unchanged, sacred):**
- Crimson `#c0392b` — nav/logo only. NOT on tiles/buttons/borders in the console. Known-person PersonDot IS crimson (identity marker, allowed).
- Action charcoal — buttons/toggles/focus rings. In dark scope focus ring = `ring-action-500`.
- Severity `#dc2626` — alarm borders/badges only.
- **Focused camera tile border:** `ring-2 ring-white/40` (white, NOT crimson).
- **Alarming camera tile:** `border-2 border-[#dc2626]` + severity pulse animation.
- **PersonDot colors:** known `#c0392b` (crimson), unknown `#ef4444` (alarm red, distinct hue), followed `#facc15` (yellow).

**Motion:** SLA bar and telemetry never animate their numbers. Banner slides in 200ms. Severity pulse is a slow 1.5s CSS `@keyframes` on border/box-shadow only. Respect `prefers-reduced-motion` (disable pulse + banner slide).

**8pt grid, `rounded-xl` cards, `rounded-[10px]` buttons, `rounded-full` badges** — same as light theme.

---

## Task 0 — liveStore Zustand slice

**Files changed:** `frontend/src/features/live/liveStore.ts` (extend existing), `liveStore.test.ts`.

**State added:**
```ts
interface LiveState {
  gridLayout: 1 | 4 | 9 | 16;
  selectedCameraId: string | null;   // highlighted in tree
  focusedCameraId: string | null;    // rendered in center HLS view
  isFollowing: boolean;
  followTrackId: string | null;
  bookmarks: { cameraId: string; tsMs: number; label?: string }[];
  alerts: LiveAlert[];               // from useLiveAlerts
  wsStatus: 'connected' | 'reconnecting' | 'offline';
  floorPlanVisible: boolean;
  // actions
  setGridLayout, setSelectedCamera, setFocusedCamera,
  startFollow(trackId), stopFollow,
  addBookmark, removeBookmark,
  upsertAlert(alert), removeAlert(id), acknowledgeAlert(id), resolveAlert(id),
  setWsStatus, toggleFloorPlan
}
```
- `upsertAlert` dedups by alert id and keeps list sorted by severity then recency.
- `acknowledgeAlert`/`resolveAlert` update local status optimistically (server call lives in the sidebar).

**TDD steps:**
- [ ] `liveStore.test.ts`: setGridLayout persists; setFocusedCamera; startFollow sets isFollowing + followTrackId; upsertAlert dedups by id; addBookmark appends; setWsStatus transitions. Confirm RED → implement → GREEN.

**Verification:**
- [ ] No cross-test state leakage (reset store in `beforeEach`).
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 1 — LivePage layout shell (forced dark, three columns)

**Files changed:** `LivePage.tsx`, `LivePage.test.tsx`.

**Layout:**
- Root: `<div class="theme-dark min-h-screen bg-[#0a0e1a] text-slate-100 flex flex-col">` — the `theme-dark` class scopes VMS dark tokens so the console is dark even when global theme is light.
- Row 1: `TopBar` (Task 8), full width, `h-14 bg-[#111827] border-b border-[#1e293b]`.
- Row 2: three-column grid `grid grid-cols-[320px_1fr_380px] flex-1 min-h-0`:
  - Left: `CameraTree` (Task 2) `bg-[#111827] border-r border-[#1e293b] overflow-hidden`
  - Center: `FocusedCameraView` (Task 4) `bg-[#0a0e1a] relative min-w-0`
  - Right: `AlertSidebar` (Task 6) `bg-[#111827] border-l border-[#1e293b] overflow-hidden`
- Row 3: `SystemStatusStrip` (Task 9) full width, `h-8 bg-[#111827] border-t border-[#1e293b]`.
- `OfflineReconnectBanner` (Task 10) is a fixed slide-from-top overlay.
- Below `md` breakpoint: collapse to single-column stack (tree becomes a Sheet toggled from TopBar) — keep responsive but operator target is desktop/wall.

**TDD steps:**
- [ ] `LivePage.test.tsx`: renders three regions with `role="region"` + aria-labels ("Camera list", "Focused camera", "Alerts"); root has dark bg class; status strip present. Confirm RED → implement → GREEN. Keep existing LivePage integration test green (adapt if layout ids changed).

**a11y:** each column is a landmark `<section aria-label>`; skip-link to alert sidebar.

**Verification:**
- [ ] Grid columns exactly `320px 1fr 380px`.
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 2 — CameraTree (left panel)

**Files changed:** `frontend/src/features/live/components/CameraTree.tsx` (new), `CameraTree.test.tsx`, reworked `CameraTile.tsx`, new hook `useCameraSnapshot.ts`.

**Behavior:**
- Header: search input (`h-9 bg-[#1a2234] border border-[#1e293b] rounded-[10px]`) + `GridLayoutSelector` (Task 3).
- Paginated tile grid: **4 columns × 3 rows = 12 tiles per page**, `grid grid-cols-4 gap-2 p-3`. Pager at bottom (`Prev`/`Next`, "Page X / N" `font-mono text-[13px]`).
- Each `CameraTile`: `aspect-video rounded-xl bg-[#1a2234] border border-[#1e293b] overflow-hidden relative cursor-pointer`. On click → `setFocusedCamera(id)` and highlight.
  - Snapshot `<img>` from `useCameraSnapshot(cameraId)` (JPEG, 2s refetch).
  - Overlay top-left: `CameraStatusBadge` (Phase 4I). Top-right: tier badge (`rounded-full text-[11px] px-2 bg-[#232d42]`).
  - Bottom gradient caption: camera name `text-xs text-slate-200 truncate`, FPS `font-mono text-[11px] text-slate-400`.
  - Focused tile: add `ring-2 ring-white/40`.
  - Alarming tile (has active alarm in store): `border-2 border-[#dc2626] animate-severity-pulse`.

**`useCameraSnapshot`:**
```ts
useQuery({
  queryKey: ['camera-snapshot', cameraId],
  queryFn: () => fetchSnapshot(cameraId),   // returns object URL / blob
  refetchInterval: 2000,
  staleTime: 0,
  refetchIntervalInBackground: false,        // pause when tab hidden
});
```

**Severity pulse keyframe** (add to `index.css`, guarded by reduced-motion):
```css
@keyframes severity-pulse {
  0%,100% { box-shadow: 0 0 0 0 rgba(220,38,38,0.0); }
  50%     { box-shadow: 0 0 0 3px rgba(220,38,38,0.45); }
}
.animate-severity-pulse { animation: severity-pulse 1.5s ease-in-out infinite; }
@media (prefers-reduced-motion: reduce) { .animate-severity-pulse { animation: none; } }
```

**TDD steps:**
- [ ] `CameraTree.test.tsx`: renders 12 tiles per page from mocked `/api/cameras`; pager advances; clicking a tile sets `focusedCameraId`; alarming camera tile gets `border-[#dc2526]`... (assert `border-[#dc2626]`); focused tile gets `ring-white/40`; snapshot img has 2s refetch (mock query). Confirm RED → implement → GREEN.

**a11y:** each tile is a `<button>` with `aria-label="Focus camera {name}"`; status badge has text alternative.

**Verification:**
- [ ] Focused border is white/40, NOT crimson.
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 3 — GridLayoutSelector

**Files changed:** `frontend/src/features/live/components/GridLayoutSelector.tsx` (new), `GridLayoutSelector.test.tsx`.

**Behavior:**
- Segmented control of four options: 1 / 4 / 9 / 16 (16 = Wall layout). Icons: single square, 2×2, 3×3, 4×4 (lucide `Square`, `Grid2x2`, `Grid3x3`, `LayoutGrid`).
- Writes `setGridLayout` in liveStore. When gridLayout > 1, the center view (Task 4) renders that many camera tiles instead of a single focused HLS view.
- Active segment: `bg-[#232d42] text-slate-100`; inactive: `text-slate-400 hover:bg-[#1a2234]`. Container: `inline-flex rounded-[10px] bg-[#111827] border border-[#1e293b] p-0.5`.

**TDD steps:**
- [ ] Test: renders 4 options; clicking "9" sets gridLayout=9; active option styled. Confirm RED → implement → GREEN.

**a11y:** `role="radiogroup"`, each option `role="radio" aria-checked`.

**Verification:**
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 4 — FocusedCameraView (center panel)

**Files changed:** reworked `FocusedCamera.tsx`, new `FocusedCameraView.tsx` (wrapper handling grid vs single), `FocusedCameraView.test.tsx`, new `useHlsStream.ts`.

**Behavior:**
- If `gridLayout === 1`: render single focused camera (HLS). Else render an N-up grid (`grid` with cols per layout: 4→`grid-cols-2`, 9→`grid-cols-3`, 16→`grid-cols-4`) of live tiles; clicking any switches to `gridLayout=1` focused on that camera.
- Single focused view:
  - `<video ref>` `w-full h-full object-contain bg-black`.
  - `useHlsStream(cameraId, videoRef)`: on cameraId change, if `Hls.isSupported()` attach `new Hls()` to the manifest URL, else fall back to native `video.src` (Safari). Destroy previous Hls instance on change/unmount.
  - Controls overlay (bottom bar, fades in on hover, `bg-gradient-to-t from-black/70`): Play/Pause, scrub −5s/+5s, Follow toggle, Snapshot, Fullscreen, Floor-plan toggle, Bookmark. Buttons `rounded-[10px] bg-[#1a2234]/80 hover:bg-[#232d42]`.
  - `BoundingBoxOverlay` (Task 5) absolutely positioned over the video.
  - Fullscreen: `containerRef.current.requestFullscreen()` toggles; track state; icon swaps.
- Empty state (no focused camera): `EmptyState` (Phase 4I) "Select a camera" centered.

**Keyboard controls (when focus view active):** Space=play/pause, ←/→ = scrub ∓5s, F=follow. (Full global shortcut wiring in Task 11; here handle the video-local ones on the container.)

**TDD steps:**
- [ ] `FocusedCameraView.test.tsx`: gridLayout=1 renders `<video>`; changing focusedCameraId re-attaches HLS (mock `useHlsStream`); Space toggles play (mock video element); Fullscreen button calls `requestFullscreen` (mock); no focused camera → EmptyState. Confirm RED → implement → GREEN. Keep existing `FocusedCamera.test.tsx` passing (migrate assertions).

**a11y:** video has `aria-label`; control buttons labeled; scrub buttons announce.

**Verification:**
- [ ] Previous Hls instance destroyed on camera change (no leak — assert cleanup called).
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 5 — BoundingBoxOverlay (SVG over video)

**Files changed:** reworked `BboxOverlay.tsx` → `BoundingBoxOverlay.tsx`, `BoundingBoxOverlay.test.tsx`, reuse `PersonDot.tsx`.

**Behavior:**
- `<svg class="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 1 1" preserveAspectRatio="none">` — normalized coordinate space so boxes track the `object-contain` video regardless of size.
- Consumes person detections from the WS stream (via a `usePersonDetections(cameraId)` selector on liveStore or a dedicated socket channel). Coordinates are normalized [0,1].
- **5fps throttle:** batch incoming detection frames; render at most every 200ms via a `requestAnimationFrame`-gated ref buffer (do NOT re-render React on every WS message — coalesce). Telemetry numbers never animate.
- Each detection: `<rect>` stroke color by identity — known `#c0392b`, unknown `#ef4444`, followed `#facc15`; `stroke-width` in vector-effect `non-scaling-stroke`. Name/GID label above box in a small `<foreignObject>` or positioned `<text>`, `font-mono text-[11px]`.
- Followed person box gets a subtle glow (`filter drop-shadow` yellow).

**TDD steps:**
- [ ] `BoundingBoxOverlay.test.tsx`: given detections, renders one `<rect>` each with correct stroke color per identity type; followed person is yellow; updates coalesce to ≤5fps (advance fake timers, assert render count). Confirm RED → implement → GREEN.

**Verification:**
- [ ] Known = crimson, unknown = `#ef4444` (distinct), followed = `#facc15`.
- [ ] Overlay is `pointer-events-none` (does not block video controls).
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 6 — AlertSidebar (right panel)

**Files changed:** reworked `AlertSidebar.tsx`, `AlertSidebar.test.tsx`, new `useLiveAlerts.ts` (socket hook), reuse/extend `useCountdown.ts` (Task 7 SLA).

**Behavior:**
- Panel: header "Active Alerts" + count badge; scrollable list (`ScrollArea` from 4J) of `AlarmCard` (Task 7); footer legend of A/R shortcuts.
- `useLiveAlerts`: single socket.io connection subscribing to the `alerts` channel; on event → `upsertAlert`; on disconnect → `setWsStatus('reconnecting'|'offline')` (drives Task 10 banner). Reuses the app's shared socket if one exists — do NOT open a second connection.
- **Auto-scroll on new alarm:** when a higher-severity alarm arrives, scroll it into view; otherwise keep operator's scroll position (don't yank on low-priority updates).
- **ARIA live region:** the list container is `aria-live="assertive" aria-relevant="additions"` so screen readers announce new critical alarms (§12).
- **Keyboard navigation:** ↑/↓ moves selection between cards; the selected card is the target of A (acknowledge) / R (resolve) global shortcuts (wired in Task 11). Selected card: `ring-2 ring-action-500`.
- Empty: `EmptyState` "No active alerts" with a calm check icon, `text-slate-400`.

**TDD steps:**
- [ ] `AlertSidebar.test.tsx`: mocked socket emits an alarm → card appears; list has `aria-live="assertive"`; ↑/↓ changes selected card; empty list renders EmptyState. Confirm RED → implement → GREEN. Keep `alerts.a11y.test.tsx` green.

**Verification:**
- [ ] Only one socket connection (assert `io()` called once across mount).
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 7 — AlarmCard + SLA bar + useCountdown

**Files changed:** reworked `AlertCard.tsx` → `AlarmCard.tsx`, `AlarmCard.test.tsx`, new `frontend/src/features/live/hooks/useCountdown.ts`, `useCountdown.test.ts`.

**AlarmCard layout:**
- Card: `rounded-xl bg-[#1a2234] p-3` with a **4px left severity border**: `border-l-4 border-l-[#dc2626]` (critical) / amber / etc. by severity.
- Row 1: alert type + camera name; timestamp `font-mono text-[13px] text-slate-400`.
- Row 2: person thumbnail/name or anomaly detail.
- **SLA bar:** thin progress bar of time remaining to `sla_deadline`. Full width, `h-1 rounded-full bg-[#232d42]`; fill width = `secondsRemaining / totalWindow`. Fill color:
  - `> 25%` → `bg-slate-400`
  - `≤ 25%` → `bg-amber-500`
  - `≤ 10%` → `bg-[#dc2626]`
  - The bar width transitions smoothly, but the numeric countdown label (`font-mono`) does NOT animate.
- Buttons: `Acknowledge (A)`, `Resolve (R)`, `Bookmark (B)`, `Export (E)` — `rounded-[10px]`, charcoal action style (`bg-action-600 hover:bg-action-500`). Acknowledge → `POST /api/alerts/{id}/acknowledge`; Resolve → `POST /api/alerts/{id}/resolve` (optimistic via store).
- Collapsible "+ N similar" group (design system §7.6) using shadcn `Collapsible` (from 4J): grouped duplicate alarms collapse under the primary card.

**`useCountdown(deadlineIso, windowSeconds)`:**
```ts
// returns { secondsRemaining, fraction, tier: 'ok'|'warn'|'crit' }
// ticks every 1000ms via setInterval; computes from Date.now() vs deadline
// tier: fraction>0.25 ok; >0.10 warn; else crit
// clamps at 0; uses UTC-safe parsing
```

**TDD steps:**
- [ ] `useCountdown.test.ts`: with fake timers, fraction decreases each second; tier flips ok→warn at 25%, warn→crit at 10%; clamps at 0. Confirm RED → implement → GREEN.
- [ ] `AlarmCard.test.tsx`: critical card has `border-l-[#dc2626]`; SLA bar fill amber at ≤25%, red at ≤10%; Acknowledge fires mocked endpoint + store update; "+N similar" Collapsible expands. Confirm RED → implement → GREEN. Keep `AlertCard.test.tsx` assertions migrated.

**Verification:**
- [ ] Severity border only on alarm cards; SLA numeric label not animated.
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 8 — TopBar (HeadCount, GPU bar, alert count, Cmd+K)

**Files changed:** reworked `TopBar.tsx`, `TopBar.test.tsx`, reuse `HeadCountBanner.tsx`.

**Layout (`h-14 bg-[#111827] border-b border-[#1e293b] px-4 flex items-center gap-4`):**
- Left: animated `VmsLogo` (crimson — the ONLY crimson in the console) + "Live" title.
- Center: **Cmd+K search trigger** — a button styled as a search field `h-9 w-72 rounded-[10px] bg-[#1a2234] border border-[#1e293b] text-slate-400 text-sm` with leading search icon and a `⌘K` kbd hint (`bg-[#232d42] rounded px-1.5 font-mono text-[11px]`). Clicking opens the Phase 4J `CommandPalette`; also opens on global Cmd/Ctrl+K.
- Right cluster:
  - **HeadCount badge** — live socket count `font-mono text-[13px]`, icon `Users`. Never animates the number.
  - **GPU utilization bar** — thin `h-1.5 w-24 rounded-full bg-[#232d42]` with fill `bg-action-500`; percentage label `font-mono text-[11px]`. Sourced from telemetry socket/poll. No animation on value.
  - **Active alerts count** — `rounded-full` badge; `bg-[#dc2626] text-white` when > 0, else muted. Clicking scrolls the alert sidebar to top.

**TDD steps:**
- [ ] `TopBar.test.tsx`: renders logo; Cmd+K trigger opens palette (mock); HeadCount reflects store value; GPU bar width matches percentage; alert count badge red when >0. Confirm RED → implement → GREEN.

**a11y:** GPU bar `role="progressbar" aria-valuenow`; alert count has `aria-label="{n} active alerts"`.

**Verification:**
- [ ] Only VmsLogo uses crimson; GPU/headcount numbers static (no transition on text).
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 9 — SystemStatusStrip (bottom bar)

**Files changed:** `frontend/src/features/live/components/SystemStatusStrip.tsx` (new), `SystemStatusStrip.test.tsx`.

**Layout (`h-8 bg-[#111827] border-t border-[#1e293b] px-4 flex items-center gap-6 text-[11px] text-slate-400`):**
- Camera count: "{online}/{total} cameras online" (online in `text-slate-200`, offline count in `text-[#dc2626]` if any).
- Head count (live) `font-mono`.
- GPU% `font-mono`.
- Last event: relative time (`date-fns`) of most recent tracking/alert event.
- Connection status dot: green `#22c55e` connected / amber reconnecting / red offline — reads `wsStatus` from store; dot + label.

**TDD steps:**
- [ ] Test: renders all five segments from store/mocked telemetry; offline cameras shown red; connection dot color follows `wsStatus`. Confirm RED → implement → GREEN.

**a11y:** connection status has text label (not color-only).

**Verification:**
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 10 — OfflineReconnectBanner

**Files changed:** reworked `DegradedBanner.tsx` → `OfflineReconnectBanner.tsx`, `OfflineReconnectBanner.test.tsx`.

**Behavior:**
- Subscribes to `wsStatus`. When `reconnecting` or `offline`, slides down from top: `fixed top-0 inset-x-0 z-50 bg-amber-500 text-slate-900 h-9 flex items-center justify-center text-sm font-medium`.
- Message: reconnecting → "Reconnecting to live feed…" with a small spinner; offline → "Live feed disconnected. Retrying…".
- Slide-in via Framer (Phase 4J) `initial={{y:-40}} animate={{y:0}} exit={{y:-40}} transition={{duration:0.2}}` wrapped in `AnimatePresence`; disabled under `prefers-reduced-motion` (just show/hide).
- Auto-dismisses when `wsStatus` returns to `connected`.

**TDD steps:**
- [ ] Test: `wsStatus='offline'` shows banner with offline text; `reconnecting` shows reconnect text; `connected` hides it. Confirm RED → implement → GREEN. Keep `DegradedBanner.test.tsx` migrated.

**a11y:** `role="status" aria-live="polite"`.

**Verification:**
- [ ] Amber, slides from top, auto-dismiss on reconnect.
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 11 — Global keyboard shortcuts + legend

**Files changed:** `frontend/src/features/live/hooks/useLiveShortcuts.ts` (new), `useLiveShortcuts.test.ts`, `frontend/src/features/live/components/ShortcutLegend.tsx` (new, `?` modal), `ShortcutLegend.test.tsx`, wire into `LivePage`.

**Shortcuts (§7 enterprise guidelines):**
| Key | Action |
|---|---|
| `A` | Acknowledge selected alarm |
| `R` | Resolve selected alarm |
| `B` | Bookmark current frame (focused camera + `Date.now()`) → `addBookmark` |
| `E` | Export clip of selected alarm/focused camera → open ClipExportDialog (Task 12) |
| `N` | Next alarm (move selection down) |
| `F` | Follow selected person / toggle follow on focused camera |
| `Space` | Play/pause focused video |
| `←` / `→` | Scrub ∓5s |
| `?` | Toggle ShortcutLegend modal |
| `Esc` | Close modal / clear selection |

**Rules:**
- Single global `keydown` listener in `useLiveShortcuts`, mounted by LivePage. **Ignore when focus is in an input/textarea/contenteditable or when the Command palette / any modal is open** (guard with a `isTypingTarget(e)` helper + open-modal check).
- Case-insensitive letters; do not trigger on modifier combos (Cmd+K reserved for palette).
- `ShortcutLegend`: shadcn `Dialog` listing all shortcuts in a two-column `kbd` grid; each key `bg-[#232d42] rounded px-1.5 font-mono text-[11px]`.

**TDD steps:**
- [ ] `useLiveShortcuts.test.ts`: `A` calls acknowledge on selected alarm; `N` advances selection; `B` adds a bookmark; `?` toggles legend; shortcuts ignored while typing in an input; ignored while palette open. Confirm RED → implement → GREEN.
- [ ] `ShortcutLegend.test.tsx`: `?` opens, Esc closes, lists all keys.

**Verification:**
- [ ] No shortcut fires while typing or when a modal/palette is open.
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 12 — ClipExportDialog

**Files changed:** `frontend/src/features/live/components/ClipExportDialog.tsx` (new), `ClipExportDialog.test.tsx`.

**Behavior:**
- shadcn `Dialog`. Fields (React Hook Form + Zod):
  - Camera (prefilled from focused camera / alarm).
  - Date range: start + end datetime pickers; default = ±30s around the alarm/bookmark timestamp. Validate end > start and window ≤ configured max.
  - Format `Select`: `MP4` | `WebM`.
  - Optional label.
- Submit → `POST /api/forensic/export` (matches audit/forensic export used elsewhere); on success show a Toast with a download link; on 501/unavailable show a clear message (forensic search text pipeline is still gated per CLAUDE.md §3 — but clip export from `forensic.py` is implemented).
- Also reachable via `E` shortcut (Task 11) and the AlarmCard Export button (Task 7).

**Design classes:** dialog panel dark (`bg-[#111827] border border-[#1e293b] rounded-xl`), inputs `bg-[#1a2234] border-[#1e293b]`, submit `bg-action-600 hover:bg-action-500 rounded-[10px]`.

**TDD steps:**
- [ ] `ClipExportDialog.test.tsx`: opens with prefilled range; Zod rejects end ≤ start; submitting valid form calls mocked `/api/forensic/export`; format select toggles MP4/WebM. Confirm RED → implement → GREEN.

**a11y:** dialog labeled; each field has a `<label>`; error messages `aria-describedby`.

**Verification:**
- [ ] Invalid range blocks submit; success emits Toast.
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 13 — Floor plan toggle + Fullscreen + Quality gate + E2E smoke

**Files changed:** `FocusedCameraView.tsx` (floor-plan overlay + fullscreen already stubbed in Task 4 — finalize), `frontend/src/features/live/components/FloorPlanOverlay.tsx` (new, Leaflet + PersonDot), `FloorPlanOverlay.test.tsx`, new E2E `frontend/e2e/live-operator.spec.ts` (Playwright), Phase 4K notes.

**Floor plan overlay:**
- Toggled by `toggleFloorPlan` (store) from the control bar and status strip. When on, render a Leaflet map (react-leaflet) sized to the focused view, with `PersonDot` markers positioned from homography-projected coordinates. Dot colors follow the identity convention (known crimson / unknown `#ef4444` / followed `#facc15`).
- Container: `absolute inset-0 z-20 bg-[#0a0e1a]/95`; close button top-right.

**Fullscreen:** finalize `requestFullscreen`/`exitFullscreen` on the center container; update icon + handle the `fullscreenchange` event to keep state in sync.

**E2E smoke (Playwright):**
- [ ] `live-operator.spec.ts`: load `/live` (mock socket + API); inject an alarm event → assert AlarmCard appears in sidebar; press `A` → assert acknowledge endpoint called and card shows acknowledged state; press `?` → legend opens.

**Final quality gate:**
- [ ] Full unit suite green (`pnpm test:run`).
- [ ] `pnpm lint && pnpm typecheck` clean.
- [ ] `pnpm build`; main-chunk gzip within budget (Live route lazy-loaded via `React.lazy`; HLS.js/Leaflet already deps). Confirm ≤ 800 kB main chunk; if the console pushes it over, code-split `/live` and its Leaflet/HLS chunks.
- [ ] Contrast check: dark surfaces vs `text-slate-100/400` meet WCAG AA (§12).
- [ ] `rg -n "bg-brand-500|border-brand-500|ring-brand" src/features/live` returns nothing (crimson only in VmsLogo + PersonDot known-color).
- [ ] Update `docs/superpowers/notes/2026-07-07-vms-phase4k-implementation-notes.md`.
- [ ] Update CLAUDE.md §3 (mark Phase 4K complete, note last milestone).
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Cross-cutting a11y checklist (enterprise guidelines §12) — verify before phase close
- [ ] Each of the three columns is a labeled landmark region.
- [ ] Alert list is `aria-live="assertive"`; new critical alarms announced.
- [ ] All controls reachable and operable by keyboard; visible focus ring (`ring-action-500` on dark).
- [ ] Connection/status conveyed by text + icon, never color alone.
- [ ] `prefers-reduced-motion` disables severity pulse + banner slide.
- [ ] Video/camera tiles have accessible labels; shortcut legend documents all keys.

## Dependency notes for the executing agent
- Task 0 (store) blocks all others.
- Task 1 (shell) blocks Tasks 2/4/6/8/9/10.
- Task 7 (AlarmCard/useCountdown) blocks the acknowledge/resolve paths used by Task 6 and Task 11.
- Task 8 depends on Phase 4J Command palette (hard dependency — 4J must be complete).
- Tasks 3/5/12/13 can proceed once their parent panels exist.
- Reuse existing components (`CameraTile`, `AlertCard`, `FocusedCamera`, `TopBar`, `BboxOverlay`, `PersonDot`, `DegradedBanner`, `HeadCountBanner`) by reworking them — do not create parallel duplicates; migrate their existing tests.
