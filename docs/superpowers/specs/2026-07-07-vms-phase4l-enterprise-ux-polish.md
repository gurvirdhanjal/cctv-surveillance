# VMS Phase 4L — Enterprise UX Polish
**Design Specification** · 2026-07-07
**Status:** Draft

---

## Preface

This spec elevates the VMS frontend from a functional operator tool to a cohesive
enterprise control surface. It is a **polish phase**, not a feature phase: no new
backend routes, no new domain data. Every section maps to one of the 20 principles
the user provided and is written so an engineer can implement it as a discrete task.

**Reading order.** This spec is a companion to, and subordinate to, the two canonical
frontend documents:

| Document | Authority for |
|---|---|
| `docs/frontend/2026-06-24-vms-design-system.md` | Colors, typography, base tokens, theme toggle, motion baseline |
| `docs/frontend/2026-05-01-vms-frontend-spec.md` | Routes, file layout, state, forms, perf budgets, error handling |

Where this spec adds a token, that token is appended to the design system's §6.1
token registry (§G below defines the additions). Where this spec contradicts an
older ad-hoc pattern, this spec wins for Phase 4L scope. Where it contradicts the
canonical design system on **color roles** (three-tier model) it does **not** win —
the three-tier model is inviolable and every section here obeys it.

**Non-negotiable inherited constraints (do not relitigate):**

- Three-tier color model: **brand brass** (`--brand-accent` `#a8752c` light / `#c8912f` dark)
  is logo + nav only; **action charcoal** for all buttons/toggles; **alarm red**
  `#dc2626` for severity only. Purple/blue/teal/violet status colors introduced in
  §K are **status semantics**, not accent colors, and are exempt from the "3 accent"
  rule (§T) because they never appear as fills on interactive controls.
- `/live` is force-dark (`data-theme="dark"` scoped). `/admin`, `/analytics`,
  `/forensic`, `/playback` default to light, user-overridable per workspace (§R).
- Token rule: never invent a Tailwind token name. Only tokens in the design system
  §6.1 registry (as extended by §G) may appear in classNames.
- `hasPermission(user.role, resource, action)` for all element-level role checks;
  never inline `user.role === 'admin'`.
- Every commit touching `frontend/` must pass `pnpm lint && pnpm typecheck && pnpm test:run`.
- Coverage: `src/shared/` ≥ 80%, `src/features/` ≥ 70%.

**Global file layout added by this phase:**

```
frontend/src/shared/
├── design-system/
│   ├── primitives/            §A — Box, Stack, Cluster, Surface primitives
│   ├── components/            existing — extended by §A, §F, §K, §L
│   ├── icons/registry.ts      §B — semantic icon registry
│   ├── tokens/                §G — elevation.css, radius.css, motion.css, states.css
│   └── motion/                §H — motionConfig.ts, useMotionPreference.ts
├── tables/                    §D — DataTable, useTableLayout, density
├── command/                   §P — CommandPalette (cmdk)
├── workspace/                 §E, §R — WorkspaceShell, useWorkspacePrefs slice
└── camera-tree/               §Q — CameraTree (virtuoso + dnd-kit)
```

---

## §A. Enterprise Design Language, not Pages

**Goal.** Every rendered element is classified into exactly one of seven roles, and
every component is composed from a small set of primitives with canonical variants.

**Scope.**
`frontend/src/shared/design-system/primitives/*`,
`frontend/src/shared/design-system/components/Button.tsx`,
`frontend/src/shared/design-system/components/Card.tsx` (new),
and a lint rule.

**Design rules (binding).**

1. The seven element roles are the closed set: **Navigation, Information, Action,
   Status, Danger, Selection, Overlay.** Every component declares its role in a
   TSDoc `@role` tag. There is no eighth role; anything that does not fit gets
   escalated via `/advisor`, not invented.
2. Role → color-tier mapping is fixed:
   - Navigation → brand brass accents only.
   - Action → action charcoal.
   - Danger → alarm red.
   - Status → status palette (§K), never on a fill of an interactive control.
   - Information, Selection, Overlay → neutral surface tokens only.
3. Canonical **Button** variants — this is the complete set; no others:
   `primary | secondary | ghost | danger | icon | toolbar | split`.
4. Canonical **Card** variants — complete set:
   `metric | health | camera | alarm | timeline | configuration`.
5. Primitives: `Box` (single styled div), `Stack` (vertical flex + gap token),
   `Cluster` (horizontal flex + wrap + gap token), `Surface` (Box + elevation token,
   §C). Every layout composes from these; raw `<div className="flex ...">` in
   feature code is disallowed for new components.

**Implementation notes.**

- `Button` props: `variant` (above), `size: 'sm'|'md'|'lg'`, `loading`, `iconLeft`,
  `iconRight`, plus for `split`: `menuItems: SplitMenuItem[]` and `onPrimary`.
  `toolbar` variant is height-32, square-ish (radius `sm`), no shadow, for floating
  action bars (§J) and table toolbars (§D).
- `Card` is a compound: `Card.Root` (variant, elevation), `Card.Header`, `Card.Body`,
  `Card.Footer`, `Card.Actions`. Variants set padding, radius, and elevation defaults;
  they do NOT set unique colors beyond the role mapping.
- `Stack`/`Cluster` `gap` prop accepts only spacing-scale tokens (§G), typed as a
  union — a raw number is a type error.

**Acceptance criteria.**

- [ ] `Button` renders all 7 variants; a Storybook (or test render) snapshot exists per variant.
- [ ] `Card` renders all 6 variants.
- [ ] An ESLint rule (`no-raw-flex-div` local rule or a `Grep`-based CI check) flags
      new `className="flex"` in `src/features/**` PRs where a primitive should be used.
- [ ] Type test: `<Stack gap={7}>` fails typecheck; `<Stack gap="16">` passes.
- [ ] Every exported component in `design-system/components` has a `@role` TSDoc tag;
      a unit test greps for its presence.

---

## §B. Semantic Icon Language

**Goal.** Each icon maps to exactly one concept; no icon is chosen ad hoc in feature code.

**Scope.** `frontend/src/shared/design-system/icons/registry.ts`, all Lucide imports in features.

**Design rules (binding).**

1. Feature code imports icons **only** from the registry, never from `lucide-react`
   directly. The registry is the single source of icon→meaning mapping.
2. Each concept has exactly one icon; each icon appears once in the registry. A
   one-to-one map, enforced by a test that fails on duplicate icon components.
3. No unlabelled icon may render outside the registry (ties to §T rule 4).

**Implementation notes.**

Registry shape:

```ts
// registry.ts
import { Monitor, Video, Circle, XCircle, BarChart3, Database,
         HeartPulse, Sparkles, Map, Play, Download /* ... */ } from 'lucide-react';

export const Icon = {
  server: Monitor,
  camera: Video,
  recording: Circle,        // rendered filled: className="fill-current"
  disconnected: XCircle,
  analytics: BarChart3,
  storage: Database,
  health: HeartPulse,
  ai: Sparkles,
  map: Map,
  playback: Play,
  export: Download,
  // ... complete the set below
} as const;

export type IconName = keyof typeof Icon;
```

Mandatory concept coverage (minimum set — add as needed, one-to-one):
`server, camera, recording, disconnected, analytics, storage, health, ai, map,
playback, export, search, filter, add, edit, delete, bookmark, ptz, live, settings,
user, users, zone, alert, audit, calendar, sync, calibrate, close, chevron-*,
grid, list, pin`.

**Acceptance criteria.**

- [ ] `registry.ts` exports `Icon` const map + `IconName` type.
- [ ] Test: no two keys reference the same Lucide component (Set of values has size === keys).
- [ ] CI check: `Grep` for `from 'lucide-react'` in `src/features/**` returns zero (registry is the only allowed importer).
- [ ] `recording` icon renders filled (`fill-current`) — visual test asserts the className.

---

## §C. Multiple Elevation Layers

**Goal.** A strict 7-layer elevation ladder with defined z-index, shadow, and background per layer.

**Scope.** `frontend/src/shared/design-system/tokens/elevation.css`, `Surface` primitive (§A).

**Design rules (binding).** The ladder is closed and ordered. Values are exact:

| Layer | Token | z-index | background token | shadow token |
|---|---|---|---|---|
| 0 Background | `--elev-bg` | `0` | `--surface-sunken` | none |
| 1 Surface | `--elev-surface` | `0` | `--surface-base` | `--shadow-1` |
| 2 Raised Card | `--elev-raised` | `1` | `--surface-raised` | `--shadow-2` |
| 3 Selected Card | `--elev-selected` | `2` | `--surface-raised` | `--shadow-2` + selection ring |
| 4 Floating Toolbar | `--elev-toolbar` | `40` | `--surface-raised` | `--shadow-3` |
| 5 Modal | `--elev-modal` | `50` | `--surface-raised` | `--shadow-4` |
| 6 Command Palette | `--elev-cmdk` | `60` | `--surface-raised` (blur, §M) | `--shadow-4` |
| 7 Toast | `--elev-toast` | `70` | `--surface-raised` | `--shadow-3` |

**Design rules.**

1. z-index values above are the **only** z-index values permitted in the codebase.
   A raw `z-[999]` or `zIndex: 100` is disallowed.
2. Selected card (layer 3) shares layer-2 background; the visual delta is the
   selection ring (`--state-selection`, §G), not a different fill.
3. Modal (50) < Command Palette (60) < Toast (70): a toast is visible over a modal;
   the command palette is visible over a modal but under a toast.

**Implementation notes.** `Surface` accepts `elevation: 0|1|2|3|4|5|6|7` and applies
the corresponding trio. Radix `Dialog`/`Popover`/`Toast` portals must be given the
matching z token via a wrapper className, not Radix defaults.

**Acceptance criteria.**

- [ ] `elevation.css` defines all 7 layers with the exact z-index values above.
- [ ] `Surface elevation={5}` renders `--shadow-4` and `z-index: 50`.
- [ ] CI `Grep` for `z-\[` and `zIndex:` in `src/**` returns only whitelisted token usages.
- [ ] Manual: toast renders above an open modal (visual test or Playwright).

---

## §D. Premium Tables

**Goal.** A single `DataTable` that provides sticky headers, resize, reorder, saved
layouts, density, keyboard nav, pinning, inline filter, bulk actions, hover preview,
and inline edit — configured per table ID.

**Scope.** `frontend/src/shared/tables/DataTable.tsx`, `useTableLayout.ts`,
`DensitySelector.tsx`, `BulkActionsToolbar.tsx`; migrate `AdminUsersPage`,
`AdminPersonsPage`, `AdminCamerasPage`, `AuditLogViewerPage` to it.

**Design rules (binding).**

1. Every table has a **stable `tableId` string**. Layout (column order, widths,
   density, pinned columns, sort) persists to `localStorage` keyed
   `vms.table.<tableId>.<userId>`. Never persist row data.
2. Density values are exactly three: `compact` (row 32px), `default` (40px),
   `relaxed` (52px). No other row heights.
3. Header is `position: sticky; top: 0` with `--elev-surface` background so it
   occludes scrolled rows.
4. Column resize: TanStack Table `columnResizeMode: 'onChange'`, min width 64px.
5. Column reorder: dnd-kit `SortableContext` over header cells; drag handle is the
   header cell itself; drop persists new order.
6. Keyboard nav: `↑`/`↓` move active row; `Enter` invokes `onRowOpen`; `Space`
   toggles row selection; `Shift+Space` range-select. Active row has `--state-focus-ring`.
7. Pinned columns: left-pin via `column.pin('left')`; pinned cells get
   `position: sticky; left: <cumulative>` and `--shadow-2` on the right edge.
8. Bulk actions toolbar (§S) appears only when `selectedCount > 0`, replacing the
   normal action bar row, animated in per §J timing (120ms slide-up).
9. Inline filter: per-column filter chip in header; opens a small popover (§M blur).
10. Inline edit: double-click a cell marked `editable` enters edit mode (input
    inherits cell width); `Enter` commits via `onCellEdit`, `Escape` cancels. Only
    columns explicitly flagged `editable: true` are editable.
11. Hover preview: rows with a `preview` render function show a `--elev-toolbar`
    card on hover after 400ms dwell (e.g. camera thumbnail, person face).
12. Virtualize the row body with `react-virtuoso` when `rowCount > 100`.

**Implementation notes.**

- Build on `@tanstack/react-table` v8 (already present). `useTableLayout(tableId)`
  returns `{ columnOrder, columnSizing, columnPinning, density, setX }` and syncs to
  localStorage via a debounced (200ms) effect.
- Density maps to a CSS var `--table-row-h` set on the table root; cell padding derives.
- Keyboard nav via a `useTableKeyboard` hook holding `activeRowIndex` state; the
  table root has `tabIndex={0}` and `role="grid"`.

**Acceptance criteria.**

- [ ] Resizing a column then reloading restores the width (localStorage round-trip test).
- [ ] Density selector switches row height to exactly 32/40/52px.
- [ ] `↓` then `Enter` on a users table opens the focused user (unit test with mocked handler).
- [ ] Selecting 2 rows shows the bulk actions toolbar; deselecting hides it.
- [ ] Pinned left column stays fixed on horizontal scroll (Playwright).
- [ ] Tables > 100 rows mount `<Virtuoso>` (assert component present).

---

## §E. Workspace Architecture

**Goal.** Replace page-centric navigation with six named workspaces, each owning its
own panel layout, toolbar, and persisted state.

**Scope.** `frontend/src/shared/workspace/WorkspaceShell.tsx`, route wiring in the
router, `useWorkspacePrefs` (§R).

**Design rules (binding).**

1. The six workspaces and their roots are fixed:
   - Operator → `/live`
   - Investigation → `/forensic`
   - Playback → `/playback`
   - Administration → `/admin`
   - Analytics → `/analytics`
   - Maintenance → `/admin/maintenance`
2. Each workspace is wrapped in `<WorkspaceShell workspaceId="operator" …>` which
   provides: the workspace toolbar slot, the resizable panel layout (§I where
   applicable), and reads/writes that workspace's persisted layout via §R.
3. Workspace layout state (panel sizes, open panels, theme override) persists per
   user per workspace: `vms.workspace.<workspaceId>.<userId>`.
4. Switching workspaces does not reset another workspace's persisted layout.

**Implementation notes.** `WorkspaceShell` props:
`workspaceId: WorkspaceId`, `toolbar: ReactNode`, `children`, `defaultTheme?:'light'|'dark'`.
Operator forces dark (`defaultTheme="dark"`, non-overridable); others default light,
overridable. `WorkspaceId` is a closed union.

**Acceptance criteria.**

- [ ] All six routes render inside a `WorkspaceShell` with the correct `workspaceId`.
- [ ] Operator workspace is dark and the theme toggle is hidden there.
- [ ] Resizing panels in `/admin`, navigating away and back, restores sizes.
- [ ] Changing `/analytics` theme does not affect `/admin` theme (independent keys).

---

## §F. Premium Camera Cards

**Goal.** Camera cards read like Apple TV cards: informative header/body/footer,
lively hover.

**Scope.** `frontend/src/features/live/components/CameraTile.tsx` and a shared
`CameraCard` in `design-system/components`.

**Design rules (binding).**

1. **Header bar:** left = `REC` badge (§K `recording` status, red filled dot +
   "REC"), right = live FPS counter (`{fps} fps`, mono, `--text-muted`).
2. **Body:** camera name (`text-base`, `--text-default`), AI status line
   (`ai` icon + state), health % (a `health` card mini-bar), location breadcrumb
   (Site › Zone, `--text-muted`).
3. **Footer:** four `toolbar` buttons — Live, Playback, PTZ, Bookmark — each
   icon+label, disabled when capability absent (e.g. PTZ disabled on fixed camera).
4. **Hover behavior (exact):** card scales to `1.02` over §H `normal` (120ms),
   metadata (location + AI line) fades in from `opacity 0.6 → 1`, quick actions
   (the footer) slide up from `y: 8 → 0` opacity `0 → 1` (§J), and a subtle glow
   is `box-shadow: --shadow-3` plus a 1px `--brand-accent` inset ring at 24% opacity.
   Scale is exactly `1.02` — not `1.03`, not `1.05`.
5. All hover motion respects `prefers-reduced-motion` (§H): reduced → no scale, no
   slide; metadata shown statically.

**Implementation notes.** Footer is the §J FloatingActionBar instance for the card.
Health mini-bar reuses the `health` Card variant's bar sub-component. FPS comes from
the existing HLS/stream stats already surfaced in Phase 4K.

**Acceptance criteria.**

- [ ] Hovering a card applies `scale(1.02)` (assert transform, not 1.05).
- [ ] PTZ button disabled for a fixed camera (capability flag).
- [ ] With `prefers-reduced-motion`, no transform/slide is applied; metadata visible.
- [ ] REC badge uses the `recording` status badge (§K), not an inline red dot.

---

## §G. Complete Design Tokens

**Goal.** Extend the token registry beyond color: radius, spacing, durations,
shadows, and interaction-state tokens — all as CSS custom properties.

**Scope.** `frontend/src/shared/design-system/tokens/{radius,spacing,motion,states}.css`,
`tailwind.config.ts` mapping, design system §6.1 update.

**Design rules (binding).** Exact values:

**Radius:** `--radius-xs:2px; --radius-sm:4px; --radius-md:6px; --radius-lg:8px;
--radius-xl:12px; --radius-2xl:16px; --radius-full:9999px;`

**Spacing scale (px):** `2, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96`.
Tailwind tokens: `space-0.5=2, space-1=4, space-2=8, space-3=12, space-4=16,
space-5=20, space-6=24, space-8=32, space-10=40, space-12=48, space-16=64,
space-20=80, space-24=96`. **No spacing value outside this scale** may appear in
new className/style.

**Animation durations:** `--dur-fast:80ms; --dur-normal:120ms; --dur-slow:180ms;
--dur-xslow:300ms;`

**Shadows.** §G supersedes the existing `--shadow-1/2/3` values in `index.css`
(which use pure-black rgba and lack a 4th tier). The new values use slate-900
rgb(15,23,42) for crisper falloff on light surfaces. The `index.css` values must be
replaced in the §G implementation commit; keeping both would create two competing
definitions of the same token name.

Light theme (exact):
```css
--shadow-1: 0 1px 2px rgba(15, 23, 42, 0.06);
--shadow-2: 0 2px 6px rgba(15, 23, 42, 0.10);
--shadow-3: 0 8px 24px rgba(15, 23, 42, 0.14);
--shadow-4: 0 16px 48px rgba(15, 23, 42, 0.20);
```
Dark theme (exact; added inside `[data-theme="dark"]` block):
```css
--shadow-1: 0 1px 3px rgba(0, 0, 0, 0.25);
--shadow-2: 0 2px 8px rgba(0, 0, 0, 0.40);
--shadow-3: 0 8px 24px rgba(0, 0, 0, 0.55);
--shadow-4: 0 16px 48px rgba(0, 0, 0, 0.65);
```

**Interaction states.**

Focus ring uses the existing neutral `--focus-ring` token (charcoal `#1e293b` light /
slate-400 `#94a3b8` dark) — **not** brand brass. Brass is logo + nav only (see
Preface inviolable constraints); putting brass on focus rings of every button, input,
and table row would violate that rule and also introduces a competing `:focus-visible`
treatment alongside the `--focus-ring` token already live in `index.css`. The two
tokens (`--focus-ring` for the ring color, `--state-focus-ring` for the full
box-shadow shorthand) are complementary: `--state-focus-ring` composes the outer
halo geometry; its color comes from `--focus-ring`.

`--state-selection` (selected table rows, active nav items) is also neutral — brass
selections outside nav items contradict the three-tier rule. Nav active indicator
uses the `borderLeft: var(--brand-accent)` motion pill (already live in AdminLayout),
not this token.

```css
/* composable box-shadow shorthand — color from --focus-ring, not --brand-accent */
--state-focus-ring:      0 0 0 2px var(--surface-base), 0 0 0 4px var(--focus-ring);
--state-selection:       inset 0 0 0 2px var(--border-strong);
--state-hover-overlay:   rgba(15, 23, 42, 0.04);   /* dark: rgba(255,255,255,0.06) */
--state-pressed-overlay: rgba(15, 23, 42, 0.08);   /* dark: rgba(255,255,255,0.10) */
```

**Acceptance criteria.**

- [ ] All tokens above exist as CSS custom properties and are mapped in `tailwind.config.ts`.
- [ ] Design system §6.1 registry updated with the new token names.
- [ ] CI `Grep` for hardcoded `px` radius/spacing in new files flags off-scale values.
- [ ] Focus ring on any focusable control matches `--state-focus-ring` (visual test).

---

## §H. Motion Guidelines

**Goal.** One enforced timing table, one easing curve, one reduced-motion hook,
one Framer config object.

**Scope.** `frontend/src/shared/design-system/motion/{motionConfig.ts,useMotionPreference.ts}`.

**Design rules (binding).**

1. Enforced timings (ms): `hover=80, dropdown=120, popover=150, modal=180,
   sidebar=180, accordion=160, page-transition=150, toast=200`.
2. Default easing is exactly `cubic-bezier(0.4, 0, 0.2, 1)` unless a spring is
   specified (§O toggles/checkboxes).
3. `useMotionPreference()` reads `prefers-reduced-motion` (and, for §M,
   `prefers-reduced-transparency`) via `matchMedia` and returns `{ reduced }`.
   When `reduced`, all durations collapse to `0ms` and springs become instant.
4. Feature code never hardcodes a duration; it references `motionConfig.<name>`.

**Implementation notes.**

```ts
export const EASE = [0.4, 0, 0.2, 1] as const;
export const motionConfig = {
  hover:   { duration: 0.08, ease: EASE },
  dropdown:{ duration: 0.12, ease: EASE },
  popover: { duration: 0.15, ease: EASE },
  modal:   { duration: 0.18, ease: EASE },
  sidebar: { duration: 0.18, ease: EASE },
  accordion:{ duration: 0.16, ease: EASE },
  page:    { duration: 0.15, ease: EASE },
  toast:   { duration: 0.20, ease: EASE },
} as const;
```

`useMotionPreference` wraps values: when reduced, a `withMotion(cfg)` helper returns
`{ duration: 0 }`. Framer `<MotionConfig reducedMotion="user">` is set at app root as
a backstop.

**Acceptance criteria.**

- [ ] `motionConfig` exports all 8 named timings with exact durations and `EASE`.
- [ ] `useMotionPreference` returns `reduced: true` when matchMedia matches (mocked test).
- [ ] With reduced motion, a modal opens with `duration: 0` (test asserts collapsed config).
- [ ] CI `Grep` for `duration: 0.` / `transition-[` literals in features flags non-token usage.

---

## §I. Live View Control Room

**Goal.** Full-bleed dark operator layout with resizable panels, an event timeline,
and a live status bar.

**Scope.** `frontend/src/features/live/*` layout, `react-resizable-panels` integration.

**Design rules (binding).**

1. Layout (top to bottom, then middle row left to right):
   `[Toolbar 40px] · [CameraTree 280px | LiveGrid 1fr | AlarmSidebar 360px] · [Timeline 120px] · [StatusBar 28px]`.
2. Toolbar and StatusBar heights are fixed (40px / 28px). CameraTree (280 default),
   AlarmSidebar (360 default), and Timeline (120 default) are **resizable** via
   `react-resizable-panels`; sizes persist per §R.
3. Timeline (120px tall) renders recent alert events as vertical marks on a time
   axis (last 60 min default), color by severity (§K/alarm red for critical). Marks
   are clickable → seek/focus.
4. StatusBar (28px) shows, left to right: GPU% , frame-drop rate, active camera
   count, head count. Each is icon + value; values update from the existing live
   stats channel (Phase 4K).
5. This layout is force-dark and inherits the Phase 4K dark surfaces.

**Implementation notes.** Use `PanelGroup`/`Panel`/`PanelResizeHandle`. Persist via
`onLayout` → `useWorkspacePrefs`. Min sizes: CameraTree 240px, AlarmSidebar 300px.
Timeline marks reuse the AlarmCard severity color mapping already in Phase 4K.

**Acceptance criteria.**

- [ ] Panels resize and persist across reload.
- [ ] StatusBar shows all four metrics wired to live stats.
- [ ] Timeline renders a mark per recent alert; clicking a mark fires a seek/focus handler.
- [ ] Toolbar is 40px, StatusBar 28px (assert computed heights).

---

## §J. Floating Action Bars

**Goal.** Remove standalone button rows from cards and table rows; surface actions
in a floating bar on hover.

**Scope.** `frontend/src/shared/design-system/components/FloatingActionBar.tsx`,
consumers in §F (camera cards) and §D (table rows).

**Design rules (binding).**

1. No standalone button row is rendered at rest on a camera card or table row.
2. On hover (or keyboard focus within the row/card), a floating bar animates in:
   Framer `initial={{ y: 8, opacity: 0 }}` → `animate={{ y: 0, opacity: 1 }}`,
   duration `motionConfig.dropdown` (120ms), ease `EASE`.
3. It dismisses on mouse leave (and on focus leaving the row) with the reverse.
4. It contains **3–5** actions, `toolbar` variant buttons, most-relevant first.
   More than 5 → overflow into a `split`/`…` menu.
5. Respect `prefers-reduced-motion`: appear/disappear instantly, no slide.

**Implementation notes.** Position `absolute` bottom-anchored inside the card/row,
`--elev-toolbar` (z 40, `--shadow-3`). Keyboard: reveal when any child of the row
has focus so keyboard users are not locked out.

**Acceptance criteria.**

- [ ] Camera card has no visible button row until hover/focus.
- [ ] Bar animates `y:8→0, opacity:0→1` at 120ms (assert config).
- [ ] Keyboard-focusing a row reveals the bar (a11y test).
- [ ] Reduced motion → instant show/hide.

---

## §K. Rich Status Badge System

**Goal.** One canonical badge set covering every camera/system state, driven by a
single `status` prop.

**Scope.** `frontend/src/shared/design-system/components/CameraStatusBadge.tsx`
(extend the existing 12-state badge from Phase 4I).

**Design rules (binding).** The status set is closed. Each has icon + label + color:

| Status | Color | Icon / motion |
|---|---|---|
| `online` | green | solid dot |
| `recording` | red | filled dot |
| `streaming` | blue | `live` icon |
| `analytics` | purple | `analytics` icon |
| `maintenance` | amber | `calendar` icon |
| `updating` | blue | spinner |
| `initializing` | gray | pulse |
| `disconnected` | gray-red | `disconnected` icon |
| `unauthorized` | orange | lock |
| `syncing` | blue | `sync` icon spin |
| `calibrating` | teal | `calibrate` icon |
| `training` | violet | `ai` icon pulse |
| `importing` | blue | `import` icon |

**Design rules.**

1. These colors are **status semantics**, not accent colors — they never fill an
   interactive control, so they are exempt from §T's 3-accent limit.
2. The status→color/icon map lives in one const; the component switches on it. No
   caller sets a badge color directly.
3. Spinner/pulse animations respect `prefers-reduced-motion` (static icon when reduced).

**Acceptance criteria.**

- [ ] `CameraStatusBadge` renders all 13 statuses with correct icon+color (snapshot per status).
- [ ] `training` uses violet, `calibrating` uses teal, `unauthorized` uses orange (assert tokens).
- [ ] Reduced motion disables spinner animation.
- [ ] Passing an unknown status is a type error (closed union).

---

## §L. Skeleton States

**Goal.** Every async state renders a shaped skeleton; no "Loading…" text in production.

**Scope.** `frontend/src/shared/design-system/components/skeletons/*`.

**Design rules (binding).**

1. Provide: `SkeletonKpiCard`, `SkeletonCameraCard`, `SkeletonTimeline`,
   `SkeletonTableRow` (accepts `columnWidths: number[]` hints), `SkeletonChart`,
   `SkeletonCameraTree`.
2. All use `animate-pulse` with a theme-aware background token
   (`--surface-sunken` fill, `--surface-raised` shimmer). No hardcoded gray.
3. `SkeletonTableRow` renders one bar per column at the hinted width so the skeleton
   matches the real table columns.
4. No production async surface may render a `"Loading..."` / `"Loading"` string.

**Acceptance criteria.**

- [ ] All six skeleton components exist and export.
- [ ] `SkeletonTableRow columnWidths={[80,200,64]}` renders three bars at those widths.
- [ ] Skeletons use `animate-pulse`; static when `prefers-reduced-motion`.
- [ ] CI `Grep` for `Loading...` / `>Loading<` in `src/features/**` returns zero.

---

## §M. Subtle Glass + Blur

**Goal.** Restrained backdrop blur on exactly four surface types; never on cards.

**Scope.** Dropdown, Command Palette (§P), Floating Toolbar (§J/§I), Context Menu.

**Design rules (binding).**

1. Blur is allowed **only** on: Dropdown, Command Palette, Floating Toolbar, Context
   Menu. Cards, modals, panels, tables must not blur.
2. The exact pattern: `backdrop-blur-md bg-surface-raised/95`. Never full glass
   (never `/50` or lower opacity), never a blurred card.
3. When `prefers-reduced-transparency` matches (via §H hook), disable blur and use
   opaque `bg-surface-raised` (full opacity).

**Acceptance criteria.**

- [ ] Dropdown/CommandPalette/FloatingToolbar/ContextMenu use `backdrop-blur-md bg-surface-raised/95`.
- [ ] Cards/modals have no `backdrop-blur` class (CI `Grep` on Card/Modal components).
- [ ] With reduced transparency, blur classes are removed and opacity is 100%.

---

## §N. Premium Navigation Structure

**Goal.** Grouped sidebar navigation with a consistent active-item treatment and a
validated animated indicator.

**Scope.** `frontend/src/features/admin/AdminLayout.tsx` sidebar and the shared nav.

**Design rules (binding).**

1. Nav groups are fixed:
   - **Monitoring:** Dashboard, Live View, Playback
   - **People:** Persons, Zones
   - **Analytics:** Detectors, Reports, Heatmap
   - **Administration:** Users, Models, Audit
2. Active item treatment: left border `--brand-accent` (2px) + background
   `--surface-sunken`. This is the only place brass fills a nav element.
3. The animated active indicator uses Framer `layoutId` spring (already present in
   Phase 4I) — **validate** it is consistent (same `layoutId`, same spring) across
   all groups; fix if divergent. Do not add a second indicator.
4. Group headers are `--text-muted`, uppercase, `text-xs`, non-interactive.

**Acceptance criteria.**

- [ ] Sidebar shows the four groups with the listed items in order.
- [ ] Active item has 2px brass left border + `--surface-sunken` background.
- [ ] A single `layoutId` drives the indicator across group switches (test asserts one layoutId).
- [ ] Items gated by permission use `hasPermission`, not role equality.

---

## §O. Micro Interactions

**Goal.** A fixed catalog of micro-interactions with exact physics.

**Scope.** `Button`, `Checkbox`, `Toggle`, sidebar, tabs, toast, tooltip primitives.

**Design rules (binding).**

1. **Button:** press `scale(0.97)` (exactly 0.97 — not 0.95, not 0.98); hover lifts
   shadow one step (`--shadow-1`→`--shadow-2`).
2. **Checkbox:** spring bounce on check — `spring(stiffness=500, damping=30)` scale
   `0.8 → 1`.
3. **Toggle:** elastic slide of the knob — `spring(stiffness=400, damping=25)`.
4. **Sidebar:** slide with `ease-out` over 180ms (`motionConfig.sidebar`).
5. **Tab underline:** animated `layoutId` (same pattern as §N).
6. **Toast:** slide-in + fade from bottom-right, 200ms (`motionConfig.toast`).
7. **Tooltip:** 80ms fade (`motionConfig.hover`).
8. Every one respects `prefers-reduced-motion` → no scale/slide/spring, instant state.

**Acceptance criteria.**

- [ ] Button active state applies `scale(0.97)` (assert exact value).
- [ ] Checkbox check uses `stiffness:500, damping:30`; toggle uses `400/25` (assert config).
- [ ] Tooltip fade duration is 80ms.
- [ ] All interactions become instant under reduced motion (matrix test).

---

## §P. Command Palette

**Goal.** A `cmdk` command palette on `Cmd/Ctrl+K` spanning entities and actions.

**Scope.** `frontend/src/shared/command/CommandPalette.tsx`, a global keybind hook,
integration with the app root.

**Design rules (binding).**

1. Library: `cmdk`. Trigger: `Cmd+K` (mac) / `Ctrl+K` (win). Elevation layer 6
   (§C), blur per §M.
2. Groups (fixed order): **Cameras, Persons, Zones, Alerts, Navigation, Actions.**
3. Each item: `icon` (from §B registry) + `label` + `shortcut hint` (right-aligned)
   + `secondary info` (muted, e.g. zone or status).
4. Fuzzy search across all entities (cmdk built-in fuzzy). Empty query shows Recent
   + Navigation.
5. Recent items (last 8 opened) persist to `localStorage` (`vms.cmdk.recent.<userId>`).
6. Keyboard: `↑`/`↓` navigate, `Enter` invoke, `Esc` or outside click closes.
7. Entity data comes from existing TanStack Query caches (no new fetch on open;
   read `queryClient` cache; lazy-fetch only on typed search miss).

**Acceptance criteria.**

- [ ] `Ctrl+K` opens the palette; `Esc` closes it.
- [ ] All six groups render with icon+label+shortcut+secondary.
- [ ] Opening an item pushes it to Recent (localStorage round-trip test).
- [ ] Palette renders at z-index 60 with blur (opaque under reduced transparency).

---

## §Q. Hierarchical Camera Tree

**Goal.** Replace the flat camera list with a Site → Building → Floor → Zone → Camera
tree: collapsible, searchable, drag-reorderable, virtualized when large.

**Scope.** `frontend/src/shared/camera-tree/CameraTree.tsx`, used by §I Live View.

**Design rules (binding).**

1. Hierarchy is fixed five levels: Site → Building → Floor → Zone → Camera.
2. Nodes collapse/expand with animated height (Framer height animation,
   `motionConfig.accordion` 160ms). Expansion state persists per §R.
3. Camera leaf shows: status dot (§K color) + name + a health bar.
4. Drag-reorder cameras **within a zone** using dnd-kit (`SortableContext` per zone).
   Cross-zone drag is not permitted in this phase.
5. Search filters the tree live: matching leaves stay, ancestors auto-expand,
   non-matching branches hide. Debounce 150ms.
6. Virtualize with `react-virtuoso` when total node count > 200.

**Implementation notes.** Reuse the Phase 4K `CameraTree` where present but upgrade
to the five-level hierarchy + reorder + virtualization. Reorder persists to the
per-user tree order (§R), not to the backend in this phase.

**Acceptance criteria.**

- [ ] Tree renders all five levels; collapse/expand animates at 160ms and persists.
- [ ] Search auto-expands ancestors of matches and hides non-matches.
- [ ] Dragging a camera within a zone reorders and persists; cross-zone drop is rejected.
- [ ] > 200 nodes → `<Virtuoso>` mounts.

---

## §R. Workspace Personalization

**Goal.** Persist per-user, per-workspace UI preferences in a single Zustand slice
with localStorage middleware.

**Scope.** `frontend/src/shared/workspace/useWorkspacePrefs.ts` (Zustand slice).

**Design rules (binding).**

1. Persisted keys (per user):
   - table layouts (order/widths/density/pinned) per `tableId` (§D)
   - theme (light/dark) per workspace (§E)
   - sidebar open/closed
   - favorite cameras (pinned in tree, §Q)
   - default grid layout (§I LiveGrid)
   - recent cameras (last 10)
   - pinned alerts
   - camera tree expansion + intra-zone order (§Q)
   - command palette recents (§P)
2. Storage key namespace: `vms.workspace.<userId>` for the slice; sub-features may
   use their own keys as specified in their sections.
3. Use Zustand `persist` middleware with `localStorage`. Version the persisted shape
   with a `version` + `migrate` so a schema bump doesn't crash on old data.
4. Never persist auth tokens, PII, or row data in this slice.

**Implementation notes.**

```ts
export const useWorkspacePrefs = create(persist<WorkspacePrefs>(
  (set) => ({ /* ... */ }),
  { name: 'vms.workspace', version: 1, migrate: (s, v) => /* ... */ s }
));
```

**Acceptance criteria.**

- [ ] Slice persists and rehydrates all listed keys.
- [ ] Bumping `version` runs `migrate` without throwing on prior-version data (test).
- [ ] No token/PII key exists in the persisted object (assertion test).
- [ ] `recentCameras` caps at 10 (FIFO eviction test).

---

## §S. Unified Action Bar

**Goal.** A consistent top-right action bar on every major page:
`[Search] [Filters] [Bulk Actions ▾] [Export] [+ Add]`.

**Scope.** `frontend/src/shared/design-system/components/ActionBar.tsx`; consumers on
admin/analytics/forensic pages.

**Design rules (binding).**

1. Order is fixed left→right: Search, Filters, Bulk Actions, Export, Add. Consistent
   `space-3` (12px) gap between controls.
2. Search is **inline** (an input in the bar), never a separate search page/route.
3. Filters open a popover (§M blur) with active filters shown as chips below/inline;
   each chip is removable.
4. Bulk Actions dropdown appears **only** when `selectedCount > 0`; hidden otherwise.
5. Export and Add are `secondary` and `primary` buttons respectively; Add uses the
   §B `add` icon.
6. The bar lives in the page header row (top-right), aligned right.

**Acceptance criteria.**

- [ ] ActionBar renders controls in the exact order with 12px gaps.
- [ ] Bulk Actions hidden at 0 selection, visible at ≥1 (test).
- [ ] Search is inline (no navigation on submit); filter chips are removable.
- [ ] Add button uses the `add` icon and `primary` variant.

---

## §T. Visual Restraint Principles

**Goal.** Encode restraint as enforceable, testable rules.

**Scope.** Lint rules / CI checks + a review checklist; applies repo-wide.

**Design rules (binding).**

1. **≤ 3 accent colors visible at once.** Accent = brand brass, action charcoal,
   alarm red. Status palette (§K) is exempt (semantics, not accents). A page must
   never introduce a fourth interactive accent color.
2. **≥ 8px gap** between any two adjacent UI elements (`space-2` minimum). No 4px or
   2px gaps between distinct elements (those are intra-component only).
3. **No orphaned buttons** — every button is in a group, toolbar, or action bar
   (§A/§J/§S). A lone `<Button>` floating in page body is disallowed.
4. **No unlabelled icon outside the §B registry** — every standalone icon has an
   `aria-label` and comes from the registry.
5. **Every empty state** has: icon + title + description + CTA (extend existing
   `EmptyState` to require all four props).
6. **Every error state** has a retry action (extend error components to require
   `onRetry`).

**Acceptance criteria.**

- [ ] `EmptyState` requires `icon`, `title`, `description`, `cta` (type-required props).
- [ ] Error boundary/error views expose an `onRetry` and render a retry button.
- [ ] CI `Grep` finds no icon import outside the registry (dup of §B check).
- [ ] Review checklist item added: "≤3 accents, ≥8px gaps, no orphan buttons" — a
      documented gate in the PR template for `frontend/` changes.

**Note on §K status hues and visual restraint.** The "≤3 accents" rule applies to
*interactive accent fills* — it is not violated by §K's 9-hue status palette because
those hues appear as small badge fills and dots, never on buttons/toggles. However,
the rule alone does not guarantee a restrained-feeling `/live` grid: a 52-camera
board where most cameras have different statuses *will* look hue-heavy even if it is
rule-compliant. Mitigations: (1) status badge sizes should be small (16–18px dot +
text, not large colored chips), (2) only show expanded status detail on hover or in
the sidebar, not on every card simultaneously, (3) do a visual gut-check once §I
ships with real camera data before concluding the restraint goal is met. Add this
gut-check as a 4M acceptance criterion.

---

## §U. New Package Additions

Add to `frontend/package.json`. Pin to a caret range on the stated major; verify
React 19 compatibility at install (all below support React 19 as of 2026-07).

| Package | Version constraint | Why |
|---|---|---|
| `sonner` | `^1.5` | Canonical toast (§O toast, §T error retries). Replaces all ad-hoc toasts. |
| `cmdk` | `^1.0` | Command palette (§P). |
| `@dnd-kit/core` + `@dnd-kit/sortable` | `^6` / `^8` | Column reorder (§D), camera reorder (§Q). |
| `react-resizable-panels` | `^2` | Resizable workspace/live panels (§E, §I). |
| `react-virtuoso` | `^4` | Virtualized tables (§D) and camera tree (§Q). |
| `echarts` + `echarts-for-react` | `^5` / `^3` | Dense dashboards; replace Recharts (§V). Note: user wrote `@apache-echarts/echarts`; the real npm package is `echarts` — use `echarts`. |
| `@xyflow/react` | `^12` | Camera topology visualization (successor to `react-flow`; use `@xyflow/react`, not the deprecated `react-flow`). Deferred consumer — see §W. |
| `leaflet` + `react-leaflet` | `^1.9` / `^4` | Floor plan / map overlays. Deferred consumer — see §W. |

Notes: bundle-size budget (frontend spec perf section) must be re-checked after
ECharts + Leaflet land; both are lazy-loaded (dynamic `import()`), not in the main
chunk. `@xyflow/react` and `leaflet` add packages now but their UI consumers are
Phase 4M (§W) — install with the phase that ships their screen if bundle budget is tight.

---

## §V. Migration Notes

1. **Toasts → Sonner.** Replace every existing `toast(...)` / ad-hoc notification
   with Sonner's `toast` from `sonner`. Mount `<Toaster>` once at app root at
   elevation layer 7 (§C, z 70), bottom-right, slide+fade 200ms (§O). Grep for old
   toast calls and migrate all; remove the old toast util.
2. **Recharts → ECharts.** Replace Recharts components on analytics/dashboard with
   `echarts-for-react`. Migration is per-chart; keep both installed only during the
   transition, then remove Recharts in the final §V commit. Charts must read theme
   tokens (§G) for series/axis colors — no hardcoded chart palettes. Lazy-load the
   ECharts bundle.
3. **CameraStatusBadge.** Extend the Phase 4I 12-state badge to the 13-state set
   (§K adds `importing`); audit all callers still compile against the closed union.
4. **CameraTile / CameraTree.** Upgrade Phase 4K components in place (§F, §Q) rather
   than forking new ones; keep the same file paths.
5. **z-index sweep.** Replace all raw z-index literals with §C tokens (one commit).
6. **Icon sweep.** Replace direct `lucide-react` imports in `src/features/**` with
   `Icon` registry references (§B), one feature area per commit.
7. **Tables.** Migrate `AdminUsersPage`, `AdminPersonsPage`, `AdminCamerasPage`,
   `AuditLogViewerPage` onto `DataTable` (§D) — one table per commit, each with its
   `tableId`.
8. **EmptyState / error views.** Tighten prop requirements (§T 5–6); fix any caller
   that omitted a CTA or retry.

Each migration item is its own commit and must keep `pnpm lint/typecheck/test:run`
green.

---

## §W. Phasing Recommendation

**Phase 4L — immediate (high impact, low risk).** Foundations others depend on, plus
low-risk polish:

- §G Complete Design Tokens (foundation — do first)
- §H Motion Guidelines (foundation)
- §C Elevation Layers (foundation)
- §B Semantic Icon Language (foundation + icon sweep)
- §A Design Language primitives + Button/Card variants
- §K Rich Status Badge (extends existing 12-state)
- §L Skeleton States
- §M Subtle Glass + Blur
- §N Premium Navigation (validate existing indicator)
- §O Micro Interactions
- §S Unified Action Bar
- §T Visual Restraint (lint/CI rules + EmptyState/error tightening)
- §V.1 Toasts → Sonner (self-contained, high value)

**Phase 4M — deferred (complex, higher risk, or hardware/data-gated).**

- §D Premium Tables (TanStack + dnd-kit + virtuoso + inline edit — largest surface,
  most regression risk; do after tokens/motion/primitives land).
- §E Workspace Architecture + §R Workspace Personalization (touches routing and all
  layouts; needs §D and §I stable first).
- §I Live View Control Room resizable refit (react-resizable-panels over the working
  Phase 4K layout — regression-sensitive on the operator console).
- §F Premium Camera Cards + §J Floating Action Bars (depend on §A primitives and
  §J bar; visually invasive on the live grid).
- §Q Hierarchical Camera Tree (five-level model + dnd-kit + virtuoso; depends on
  backend hierarchy fields being present — confirm Site/Building/Floor availability
  before starting).
- §P Command Palette (depends on §B icons and cross-feature query caches).
- §V.2 Recharts → ECharts (per-chart migration; bundle-budget re-check).
- Topology (`@xyflow/react`) and floor-plan/map (`leaflet`) consumers — packages
  listed in §U but their screens are out of scope for 4L/4M polish; schedule with the
  analytics/topology feature phase.

**Sequencing rule.** The four foundation sections (§G, §H, §C, §B) must merge before
any §W-deferred item, because tables, cards, live view, and the palette all consume
their tokens. Do not start a 4M item whose foundation is unmerged.

---

**End of Phase 4L spec.**
