# Phase 4M — Interactive Surfaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: NOT STARTED**

**Goal:** Deliver the eight complex, data-interactive sections of the Phase 4L spec that
were deferred due to higher regression risk: Premium Tables (§D), Workspace Architecture
(§E), Workspace Personalization (§R), Live View resizable refit (§I), Premium Camera
Cards + Floating Action Bars (§F + §J), Hierarchical Camera Tree (§Q), Command Palette
upgrade (§P), and ECharts migration (§V.2). Also cleans up Phase 4L deferred items:
old Toast/ToastProvider removal and three missing skeleton composites.

**Architecture:**
- Every section builds on the §G/§H/§A/§B/§K foundations already shipped in Phase 4L.
- Dependency order is: §R → §D → §E → §I → §F+§J → §Q → §P → §V.2 → cleanup.
- §Q requires backend nullable columns (`site_name`, `building_name`, `floor_name`) on
  the Camera table — Task 8 includes the Alembic migration before the frontend work.
- No new backend routes — all new data comes from existing API endpoints.

**Tech Stack:**
- `@tanstack/react-table` v8 (already installed) — §D DataTable upgrade
- `@dnd-kit/core` + `@dnd-kit/sortable` (already installed) — §D column reorder, §Q drag
- `react-virtuoso` (already installed) — §D + §Q virtualization
- `react-resizable-panels` (already installed) — §I panel resizing
- `zustand` v4 with `persist` middleware (already installed) — §R
- `cmdk` v1 (already installed) — §P command palette
- `echarts` + `echarts-for-react` (already installed) — §V.2 chart migration
- `framer-motion` (already installed) — §F + §J hover animations
- All packages confirmed present in `frontend/package.json`

**Spec refs:**
- `docs/superpowers/specs/2026-07-07-vms-phase4l-enterprise-ux-polish.md`
  §D, §E, §F, §I, §J, §P, §Q, §R, §V.2, §W (phasing)
- `docs/frontend/2026-06-24-vms-design-system.md`
- `docs/frontend/2026-05-01-vms-frontend-spec.md`

**Blocked items (do NOT start without resolving):**
- §Q five-level tree requires `site_name`/`building_name`/`floor_name` on Camera.
  Task 8 opens with the Alembic migration; frontend work follows in the same task.
- Do NOT start §E WorkspaceShell before §D DataTable (Task 2+3) is merged — §E
  consumes `useWorkspacePrefs` (§R), which in turn stores table layout from §D.
- Do NOT start §I until §E WorkspaceShell is complete — the live workspace wraps §I.

---

## Pre-flight: gap audit

Before Task 1 begins, verify:
- [ ] `pnpm test:run` passes at baseline (should be 722/722).
- [ ] `EmptyState` props audit: current `action?: React.ReactNode` must become
  `cta: React.ReactNode` (required, per §T rule 5). Note all callers before changing.
- [ ] Confirm no `from 'recharts'` remains outside `analytics/components/` (run grep).
- [ ] Confirm `@xyflow/react` is NOT needed for this phase (topology is deferred to Phase 6).

---

## Task 1: §R Workspace Personalization — Zustand persist slice

**Goal:** A single Zustand slice backed by localStorage that all later tasks write to.
Build it first so §D, §E, §I, §Q all have the same persistence API.

- [ ] **Test (failing):** Write `frontend/src/shared/workspace/useWorkspacePrefs.test.ts`.
  Assert: slice exports `useWorkspacePrefs`; `recentCameras` caps at 10 (FIFO eviction);
  bumping `version` from 0→1 runs `migrate` without throwing; no `token`/`rtsp_url`/
  `password` key exists in the persisted shape; slice rehydrates after `localStorage.setItem`.

- [ ] **Implement:** Create `frontend/src/shared/workspace/useWorkspacePrefs.ts`.

  ```ts
  export interface WorkspacePrefs {
    version: number          // migration version
    tableLayouts: Record<string, TableLayoutPrefs>   // keyed tableId_userId
    workspaceThemes: Record<string, 'light' | 'dark'>  // keyed workspaceId
    sidebarOpen: boolean
    favoriteCameraIds: number[]
    defaultGridLayout: string
    recentCameraIds: number[]   // max 10, FIFO
    pinnedAlertIds: string[]
    treeExpansion: Record<string, boolean>   // keyed nodeId
    treeOrder: Record<string, number[]>      // keyed zoneId → cameraId[]
    cmdkRecents: CmdkRecentItem[]            // max 8
  }

  export interface TableLayoutPrefs {
    columnOrder: string[]
    columnSizing: Record<string, number>
    columnPinning: { left: string[]; right: string[] }
    density: 'compact' | 'default' | 'relaxed'
    sorting: Array<{ id: string; desc: boolean }>
  }
  ```

  Use Zustand `persist` with `localStorage`, `name: 'vms.workspace'`, `version: 1`,
  and a `migrate` function that coerces unknown versions to the current shape without
  throwing. Export `RECENT_CAMERAS_MAX = 10`, `CMDK_RECENTS_MAX = 8` as constants.
  Export action `pushRecentCamera(id)` that FIFO-evicts past the cap.

- [ ] **Verify:** `pnpm test:run` passes (new tests green, baseline unchanged).
- [ ] **Commit:** `feat: phase 4M task 1 -- §R workspace prefs Zustand persist slice`

---

## Task 2: §D DataTable core — resize, density, sticky header, localStorage

**Goal:** Upgrade the existing `DataTable.tsx` (196 lines) to the §D spec foundation:
sticky header, density prop (compact/default/relaxed), column resize via TanStack
`columnResizeMode: 'onChange'`, and `useTableLayout` hook persisting to `useWorkspacePrefs`.

**Prerequisite:** Task 1 merged.

- [ ] **Test (failing):** Write `frontend/src/shared/design-system/components/DataTable.test.tsx`
  (new spec-driven tests, not the old ones). Assert:
  - Resizing column width via `onColumnSizingChange` then calling `useTableLayout.restore`
    returns the saved width (localStorage round-trip via mocked `useWorkspacePrefs`).
  - Density `compact` sets `--table-row-h: 32px`; `default` = 40px; `relaxed` = 52px
    (assert CSS var on the table root).
  - Header row has `position: sticky; top: 0` (assert className contains `sticky top-0`).
  - `tableId` prop is required (TS type test: omitting it fails typecheck).

- [ ] **Implement `useTableLayout` hook:** `frontend/src/shared/tables/useTableLayout.ts`.
  Accepts `(tableId: string, userId: string)`.
  Reads/writes `workspacePrefs.tableLayouts[`${tableId}_${userId}`]` via `useWorkspacePrefs`.
  Returns `{ columnOrder, columnSizing, columnPinning, density, sorting, set* }`.
  Debounce writes 200ms (use `useEffect` + `setTimeout`).

- [ ] **Upgrade `DataTable.tsx`:**
  - Add required `tableId: string` prop.
  - Add `density?: 'compact' | 'default' | 'relaxed'` (default `'default'`).
  - Set `--table-row-h` CSS var on the table root element; all `<td>` height derives from it.
  - Header `<thead>` gets `className="sticky top-0 z-10 bg-surface-raised"`.
  - Wire `columnResizeMode: 'onChange'` + `onColumnSizingChange` → `useTableLayout`.
  - Wire `onColumnOrderChange` → `useTableLayout`.
  - Restore column sizing + order on mount from `useTableLayout`.
  - Add `DensitySelector` inline control (a 3-state toggle in the table toolbar).

- [ ] **Verify:** `pnpm test:run` passes. `pnpm typecheck` clean.
- [ ] **Commit:** `feat: phase 4M task 2 -- §D DataTable core: resize, density, sticky header, localStorage`

---

## Task 3: §D DataTable advanced — reorder, pinning, keyboard nav, bulk actions, filter, Virtuoso

**Goal:** Complete the §D DataTable spec: column drag-reorder (dnd-kit), column pinning
(sticky left), keyboard navigation (`↑`/`↓`/`Enter`/`Space`/`Shift+Space`), bulk
actions toolbar (appears only when `selectedCount > 0`), per-column inline filter
popover, and react-virtuoso virtualization when `rowCount > 100`.

**Prerequisite:** Task 2 merged.

- [ ] **Test (failing):** Extend `DataTable.test.tsx`. New assertions:
  - `↓` moves active row index; `Enter` calls `onRowOpen` with the row (mock handler).
  - `Space` toggles row selection on the active row.
  - `selectedCount > 0` renders `BulkActionsToolbar`; deselecting all hides it.
  - Passing `columnDefs` with `pin: 'left'` results in a cell with `position: sticky`.
  - `data` array of 101 items mounts a `<Virtuoso>` component (assert presence).

- [ ] **Implement `useTableKeyboard` hook:**
  `frontend/src/shared/tables/useTableKeyboard.ts`.
  Holds `activeRowIndex` state; handles `↑`/`↓`/`Enter`/`Space`/`Shift+Space`.
  The table root has `tabIndex={0}` + `role="grid"`.

- [ ] **Implement `BulkActionsToolbar`:**
  `frontend/src/shared/tables/BulkActionsToolbar.tsx`.
  Uses `ActionBar` (§S) from Phase 4L; shown only when `selectedCount > 0`.
  Slide-up animation: `initial={{ y: 8, opacity: 0 }}`, `animate={{ y: 0, opacity: 1 }}`,
  `duration: 0.12` (§H `dropdown`).
  Props: `selectedCount`, `actions: Array<{ label, icon, onClick }>`.

- [ ] **Implement column drag-reorder:**
  Wrap `<th>` cells in `@dnd-kit/sortable` `SortableContext`; drag handle is the header cell.
  On `onDragEnd` → `setColumnOrder` → `useTableLayout.set`.
  Drag handle renders `GripVertical` icon from §B registry on hover.

- [ ] **Implement column pinning:**
  TanStack `columnPinning` state wired to `useTableLayout`.
  Pinned-left cells: `position: sticky; left: <cumulative-offset>px; z-index: 1;
  box-shadow: 1px 0 0 var(--border-default)`.

- [ ] **Implement per-column inline filter:**
  Filter chip in column header; clicking opens a `Popover` (with `glass-dropdown`)
  containing a controlled `<input>`. Filter state lives in TanStack column filters.
  Active filter chip is shown below the toolbar with an ×-close button.

- [ ] **Implement Virtuoso virtualization:**
  When `data.length > 100`, replace the `<tbody>` with `<Virtuoso>` (TableVirtuoso
  component). Use `fixedHeaderContent` for the sticky `<thead>`. Otherwise keep the
  existing `<tbody>` path.

- [ ] **Verify:** `pnpm test:run` passes. `pnpm typecheck` clean.
  Manual: bulk toolbar slides up; drag reorder works; >100 rows uses Virtuoso.
- [ ] **Commit:** `feat: phase 4M task 3 -- §D DataTable reorder, pinning, keyboard nav, bulk actions, filter, Virtuoso`

---

## Task 4: §D table migrations — four admin pages

**Goal:** Migrate all four spec-required admin pages to the upgraded DataTable, each
with a stable `tableId`, appropriate density default, and column pinning where useful.
Also tighten `EmptyState` per §T rule 5 (require `cta` prop).

**Prerequisite:** Task 3 merged.

- [ ] **Tighten `EmptyState` (§T rule 5):**
  - Read `frontend/src/shared/design-system/components/EmptyState.tsx`.
  - Change `action?: React.ReactNode` → `cta: React.ReactNode` (required).
  - Rename prop from `action` to `cta` in component body.
  - Audit all callers with `grep -r "EmptyState" frontend/src/features/`; fix each one
    to pass `cta={...}`. Current callers use the optional `action` — each must gain a CTA.
  - Update `EmptyState.test.tsx`.

- [ ] **`AdminUsersPage`** → `tableId="admin-users"`, density `default`,
  pin `username` left. Add `onRowOpen` → navigate to user detail.
  Test: existing `AdminUsersPage.test.tsx` still green.

- [ ] **`AdminPersonsPage`** → `tableId="admin-persons"`, density `default`,
  pin `name` left. Add `onRowOpen` → navigate to person detail.
  Test: existing `AdminPersonsPage.test.tsx` still green.

- [ ] **`AdminCamerasPage`** → `tableId="admin-cameras"`, density `compact`
  (dense ops table), pin `name` left. Add `onRowOpen` → navigate to camera detail.
  Test: existing `AdminCamerasPage.test.tsx` still green.

- [ ] **`AuditLogViewerPage`** → `tableId="audit-log"`, density `compact`,
  no pinning (all columns informational). Virtuoso will activate automatically
  when page loads many rows (>100 threshold).
  Test: existing `AuditLogViewerPage.test.tsx` still green.

- [ ] **Verify:** `pnpm test:run` all green. `pnpm typecheck` clean.
- [ ] **Commit:** `feat: phase 4M task 4 -- §D table migrations + §T EmptyState cta required`

---

## Task 5: §E Workspace Architecture — WorkspaceShell + route wiring

**Goal:** Wrap all six named workspaces in `WorkspaceShell`, provide per-workspace
toolbar + theme override, and wire the persisted panel layout via `useWorkspacePrefs`.

**Prerequisite:** Task 1 (§R) merged.

- [ ] **Test (failing):** Write `frontend/src/shared/workspace/WorkspaceShell.test.tsx`.
  Assert: renders `data-workspace-id` attribute; `workspaceId="operator"` sets
  `data-theme="dark"` and hides the theme toggle; switching workspaceId does not
  reset another workspace's stored prefs (mock store, write one key, switch, verify).

- [ ] **Implement `WorkspaceShell`:**
  `frontend/src/shared/workspace/WorkspaceShell.tsx`
  Props: `workspaceId: WorkspaceId`, `toolbar?: ReactNode`, `children`,
  `defaultTheme?: 'light' | 'dark'`.
  `WorkspaceId` = closed union: `'operator' | 'investigation' | 'playback' |
  'administration' | 'analytics' | 'maintenance'`.
  Reads `workspaceThemes[workspaceId]` from `useWorkspacePrefs`; applies as
  `data-theme` on the root div (overrides global theme within this workspace).
  `operator` workspace: always `data-theme="dark"`, theme toggle hidden (omit from toolbar).
  Persists `workspaceThemes` on theme-toggle click.

- [ ] **Wire all six routes** in `App.tsx` / `routes.tsx`:
  - `/live` → `<WorkspaceShell workspaceId="operator">`
  - `/forensic` → `<WorkspaceShell workspaceId="investigation">`
  - `/playback` → `<WorkspaceShell workspaceId="playback">`
  - `/admin/*` → `<WorkspaceShell workspaceId="administration">`
  - `/analytics/*` → `<WorkspaceShell workspaceId="analytics">`
  - `/admin/maintenance` → `<WorkspaceShell workspaceId="maintenance">`

- [ ] **Verify:** `pnpm test:run` all green. Theme toggle hidden on `/live`; visible on `/admin`.
- [ ] **Commit:** `feat: phase 4M task 5 -- §E WorkspaceShell + six-workspace route wiring`

---

## Task 6: §I Live View resizable refit + Timeline + StatusBar

**Goal:** Add `react-resizable-panels` to the live layout (replacing hardcoded widths),
add the 120px alert Timeline row above the status bar, and wire panel sizes to
`useWorkspacePrefs`.

**Prerequisite:** Task 5 merged.

**Spec §I layout (exact):**
```
[TopBar 40px]
[CameraTree 280px | LiveGrid 1fr | AlarmSidebar 360px]  ← resizable
[Timeline 120px]                                        ← new
[StatusBar 28px]                                        ← existing SystemStatusStrip
```

- [ ] **Test (failing):** Write `frontend/src/features/live/LivePage.test.tsx` additions.
  Assert: `PanelGroup` renders with `direction="horizontal"` and three `Panel` children;
  `ResizeHandle` renders between panels; layout changes call `onLayout` (mock).
  Timeline row has height exactly 120px (assert inline style or CSS var).
  StatusBar row has height 28px.

- [ ] **Implement `AlertTimeline`:**
  `frontend/src/features/live/components/AlertTimeline.tsx`
  Shows last 60 minutes of alerts as vertical marks on a horizontal time axis.
  Mark color per severity: CRITICAL = `var(--alarm-red)`, HIGH = amber, MEDIUM = yellow,
  LOW = `var(--text-muted)`. Clicking a mark calls `onSeek(alertId)`.
  Width fills parent; height fixed 120px. Marks positioned by `% = (now - ts) / 3600`.
  Data from `useLiveStore`'s `alerts` array (already fetched in Phase 4K).

- [ ] **Upgrade `LivePage.tsx`:**
  Replace `style={{ gridTemplateColumns: '320px 1fr 380px' }}` with `PanelGroup`:
  ```tsx
  <PanelGroup direction="horizontal" onLayout={saveLayout}>
    <Panel defaultSize={22} minSize={16} id="camera-tree">
      <CameraTree />
    </Panel>
    <PanelResizeHandle className="w-px bg-[#1e293b] hover:bg-[var(--brand-accent)] transition-colors" />
    <Panel id="focused">
      <FocusedCamera ... />
    </Panel>
    <PanelResizeHandle className="w-px bg-[#1e293b] hover:bg-[var(--brand-accent)] transition-colors" />
    <Panel defaultSize={26} minSize={20} id="alerts">
      <AlertSidebar />
    </Panel>
  </PanelGroup>
  ```
  Add `<AlertTimeline />` row below the panel group, fixed 120px.
  `onLayout` → `useWorkspacePrefs().setTableLayouts` (reuse existing key shape or add
  `panelLayouts: Record<string, number[]>` to the prefs).
  Restore panel sizes from prefs on mount.

- [ ] **Add `SkeletonTimeline` composite** (deferred from Phase 4L):
  `frontend/src/shared/design-system/components/Skeleton.tsx` — add `SkeletonTimeline`.
  Renders a full-width bar + 8 evenly spaced `Skeleton` marks.

- [ ] **Verify:** `pnpm test:run` all green. Manual: resize CameraTree, reload → size restored.
- [ ] **Commit:** `feat: phase 4M task 6 -- §I live view resizable panels + alert timeline`

---

## Task 7: §F + §J Premium Camera Cards + FloatingActionBar

**Goal:** Upgrade `CameraTile` to the §F spec (header bar, body with health/AI, animated
footer), and build the reusable `FloatingActionBar` component (§J) used by cards and table rows.

**Spec §F exact hover behavior:**
- Scale `1.02` (not 1.03, not 1.05) over `motionConfig.hover` (80ms)
- Metadata fades `opacity 0.6 → 1`
- Footer (FloatingActionBar) slides `y: 8 → 0, opacity: 0 → 1`, 120ms (§H `dropdown`)
- Glow: `box-shadow: --shadow-3` + 1px inset `--brand-accent` at 24% opacity
- All motion guarded by `useReducedMotion()`

- [ ] **Test (failing):** Write `frontend/src/shared/design-system/components/FloatingActionBar.test.tsx`.
  Assert: hidden at rest (no `data-visible`); revealed on `onMouseEnter` / on any child
  focus; animates with `y: 8 → 0, opacity: 0 → 1` props; `reduced motion` → instant show.
  Write `frontend/src/features/live/components/CameraTile.test.tsx` additions:
  scale is `1.02` constant (assert exported `CAMERA_TILE_HOVER_SCALE === 1.02`);
  PTZ button disabled when `capabilities.ptz === false`; REC badge uses `recording` status.

- [ ] **Implement `FloatingActionBar`:**
  `frontend/src/shared/design-system/components/FloatingActionBar.tsx`
  Position `absolute bottom-0 left-0 right-0`; `--elev-toolbar` (`z-40`, `--shadow-3`).
  Framer `motion.div` with `initial={{ y: 8, opacity: 0 }}` / `animate={{ y: 0, opacity: 1 }}`.
  Revealed via `data-hovered` parent attribute (set on card/row `onMouseEnter`/`onFocus`
  within, cleared on `onMouseLeave`/`onBlur` outside).
  Max 5 `toolbar`-variant buttons; overflow into split/… menu.
  Props: `actions: FloatingAction[]` where `FloatingAction = { icon, label, onClick, disabled? }`.

- [ ] **Upgrade `CameraTile.tsx`:**
  Wrap in `motion.div` with `whileHover={{ scale: 1.02 }}`.
  Export `export const CAMERA_TILE_HOVER_SCALE = 1.02` for test assertion.
  Add header bar: left = `CameraStatusBadge status="recording"` (conditional), right = FPS.
  Add body: camera name, AI status line (`Icon.ai` + state string), health mini-bar
  (a single `<div>` with `width: ${healthPct}%` and `bg-green-500` fill), location
  (zone name, `--text-muted`).
  Add `FloatingActionBar` with actions: Live, Playback, PTZ (disabled if `!hasPtz`), Bookmark.
  PTZ capability comes from `camera.capability_tier` (`'FULL'` = PTZ capable).
  Hover glow: `filter: drop-shadow(0 0 8px rgb(var(--brand-accent-rgb) / 0.24))`.
  Reduced motion: no scale, no slide, footer visible statically.

- [ ] **Add `SkeletonCameraCard` update:** verify the composite from Phase 4L matches
  the new CameraTile structure (update if the header/body shape changed).

- [ ] **Verify:** `pnpm test:run` all green. `pnpm typecheck` clean.
- [ ] **Commit:** `feat: phase 4M task 7 -- §F premium camera cards + §J FloatingActionBar`

---

## Task 8: §Q Hierarchical Camera Tree (backend migration + frontend 5-level tree)

**Goal:** Add nullable hierarchy columns to the Camera model so the frontend can
display a Site → Building → Floor → Zone → Camera tree. Implement the tree with
animated collapse, search, drag-reorder within zones, and Virtuoso virtualization.

**Backend prerequisite:** Camera model currently has no `site_name`, `building_name`,
`floor_name` fields. The spec requires them (§Q note). Add them as nullable TEXT columns
so existing cameras default to NULL (displayed as "Default Site" / "Default Building" /
"Ground Floor" groupings in the frontend).

- [ ] **Alembic migration:** `alembic revision -m "add camera hierarchy fields"`.
  ```python
  # upgrade
  op.add_column('cameras', sa.Column('site_name', sa.String(200), nullable=True))
  op.add_column('cameras', sa.Column('building_name', sa.String(200), nullable=True))
  op.add_column('cameras', sa.Column('floor_name', sa.String(200), nullable=True))
  # downgrade
  op.drop_column('cameras', 'floor_name')
  op.drop_column('cameras', 'building_name')
  op.drop_column('cameras', 'site_name')
  ```
  Apply: `alembic upgrade head`. Run `pytest tests/` to confirm green.

- [ ] **Update ORM model** (`vms/db/models.py`): add the three fields to `Camera`.
- [ ] **Update `CameraResponse` schema** (`vms/api/schemas.py`): add
  `site_name: str | None = None`, `building_name: str | None = None`,
  `floor_name: str | None = None`.
- [ ] **Update API response test** in `tests/api/test_cameras.py`: assert new fields
  exist in response (nullable; may be null for existing test cameras).
- [ ] **Run Python quality gate:**
  ```powershell
  black vms/ tests/; ruff check vms/ tests/; mypy vms/; pytest --cov=vms
  ```

- [ ] **Test (failing):** Write `frontend/src/features/live/components/CameraTree.test.tsx`
  additions. Assert:
  - Tree renders 5 levels when hierarchy data present.
  - A node with `site_name=null` groups under "Default Site".
  - Collapse/expand changes `aria-expanded`.
  - Search "cam" auto-expands ancestors and hides non-matching branches.
  - Dragging camera within a zone calls `useWorkspacePrefs().setTreeOrder`
    (mock the store).
  - 201 cameras mount `<Virtuoso>` (assert presence).

- [ ] **Implement upgraded `CameraTree.tsx`:**
  Replace flat-tile implementation with a true 5-level collapsible tree.

  **Data grouping** (client-side, from the flat camera list):
  Group cameras into `Map<site, Map<building, Map<floor, Map<zone, Camera[]>>>>`.
  Use `site_name ?? 'Default Site'`, `building_name ?? 'Default Building'`,
  `floor_name ?? 'Ground Floor'`, `zone_name ?? 'Unzoned'` as fallbacks.

  **Tree node component** (`CameraTreeNode`): renders a row with collapse indicator
  (Framer animated height, `motionConfig.accordion` 160ms), status dot (§K color),
  name, health bar for camera leaves.

  **Expansion persistence:** reads/writes `useWorkspacePrefs().treeExpansion`.

  **Drag-reorder within zone:** dnd-kit `SortableContext` per zone; persists to
  `useWorkspacePrefs().treeOrder`. Cross-zone drop rejected (validate on `onDragEnd`).

  **Search:** debounced 150ms; matching leaves kept; ancestor nodes auto-expand;
  non-matching branches hidden via CSS `display: none` (not unmounted, to preserve
  expansion state).

  **Virtuoso:** when total node count > 200, render with `Virtuoso`'s `VirtuosoTree`
  or flatten + `TableVirtuoso` (use flat row list approach for simplicity).

  **`SkeletonCameraTree` composite:** Add to `Skeleton.tsx` — renders 3 group headers
  + 4 camera row skeletons.

- [ ] **Verify:** `pnpm test:run` all green. `pnpm typecheck` clean. `pytest` green.
- [ ] **Commit:** `feat: phase 4M task 8 -- §Q camera hierarchy migration + 5-level tree upgrade`

---

## Task 9: §P Command Palette upgrade

**Goal:** Upgrade the existing `CommandPalette` (in `src/components/`) to the §P spec:
move to `src/shared/command/`, add all 6 required groups, Recent (localStorage via
`useWorkspacePrefs`), secondary info on items, and use §B icons throughout.

**Current state:** CommandPalette lives in `src/components/CommandPalette.tsx`, has
3 groups (People, Cameras, Navigate+Admin), uses direct `lucide-react` imports, and
has no Recent persistence.

- [ ] **Test (failing):** Write `frontend/src/shared/command/CommandPalette.test.tsx`.
  Assert: Ctrl+K opens the palette; Escape closes; all 6 group headings render
  (`Cameras`, `Persons`, `Zones`, `Alerts`, `Navigation`, `Actions`);
  opening a camera item adds it to `cmdkRecents` in prefs store (mock);
  palette renders at `z-[60]` (elevation layer 6) with `glass-cmdk` class;
  palette is opaque under reduced transparency (assert no `backdrop-blur` when
  `prefers-reduced-transparency` mocked as matching).

- [ ] **Implement upgraded `CommandPalette`:**
  New file: `frontend/src/shared/command/CommandPalette.tsx`.
  Old `src/components/CommandPalette.tsx` becomes a re-export of the new path
  (to avoid breaking the import in `App.tsx`) — update `App.tsx` import after.

  **6 groups (fixed order per §P spec):**
  1. **Cameras** — from `useQuery(['cameras'])`, up to 5, filter by search.
     Secondary info: zone name + status badge.
  2. **Persons** — from `useQuery(['cmd-persons', query])` (enabled when query ≥ 2 chars).
     Secondary info: employee ID.
  3. **Zones** — from `useQuery(['zones'])`, static list, filter by search.
     Secondary info: floor name.
  4. **Alerts** — from `useLiveStore().alerts` (live cache), last 5 open alerts.
     Secondary info: severity + camera name.
  5. **Navigation** — fixed list of top-level routes with keyboard shortcuts.
  6. **Actions** — context-sensitive quick actions (e.g. "Enrol New Person", "Add Camera").

  **Recent items:** when empty query, show last 8 items from `cmdkRecents` (prefs store)
  before the 6 groups. `pushCmdkRecent(item)` on item selection.

  **§B icons:** replace all direct `lucide-react` imports with `Icon.*` from the registry.

  **Glass + elevation:** wrap in a container with `z-[60] glass-cmdk shadow-4 rounded-xl`.

  **Secondary info:** render as `<span className="ml-auto text-xs text-text-muted">`.

- [ ] **Update `App.tsx`** import of `CommandPalette` to use the new path.
- [ ] **Verify:** `pnpm test:run` all green. Ctrl+K works in manual browser test.
- [ ] **Commit:** `feat: phase 4M task 9 -- §P command palette upgrade (6 groups, Recent, glass, §B icons)`

---

## Task 10: §V.2 Recharts → ECharts migration

**Goal:** Replace all three Recharts charts with ECharts (`echarts-for-react`), each
reading theme tokens from CSS variables for series/axis colors. Lazy-load the ECharts
bundle. Remove Recharts from `package.json` at the end.

**Scope:** 3 files currently importing from `recharts`:
- `frontend/src/features/analytics/components/AlertVolumeChart.tsx`
- `frontend/src/features/analytics/components/DwellChart.tsx`
- `frontend/src/features/analytics/components/HeadCountChart.tsx`

**Bundle rule:** ECharts is lazy-loaded via `React.lazy` + `Suspense`.
Wrapper: `frontend/src/shared/charts/EChartsWrapper.tsx` — a thin lazy wrapper that
forwards the `option` prop to `echarts-for-react`'s `ReactECharts`.

- [ ] **Test (failing):** For each chart, update its `.test.tsx` to assert it renders
  without error and that the rendered element does NOT contain `recharts` className
  (e.g., `recharts-wrapper`). Add `SkeletonChart` test.

- [ ] **Implement `EChartsWrapper`:**
  `frontend/src/shared/charts/EChartsWrapper.tsx`
  ```tsx
  const ReactECharts = React.lazy(() => import('echarts-for-react'))
  export function EChartsWrapper({ option, style, className }: EChartsWrapperProps) {
    return (
      <Suspense fallback={<SkeletonChart className={className} style={style} />}>
        <ReactECharts option={option} style={style} notMerge lazyUpdate />
      </Suspense>
    )
  }
  ```
  Theme helper `useChartTheme()`: reads CSS vars `--text-primary`, `--text-muted`,
  `--border-default`, `--surface-raised` from `getComputedStyle(document.body)` and
  returns an ECharts theme object (axis labels, grid lines, background).

- [ ] **Migrate `AlertVolumeChart.tsx`:** replace Recharts with ECharts `bar` series.
  Colors from `--alarm-red` for critical, amber for high, yellow for medium, gray for low.

- [ ] **Migrate `DwellChart.tsx`:** replace Recharts with ECharts `scatter` or `bar`.
  Color from `--text-primary` series.

- [ ] **Migrate `HeadCountChart.tsx`:** replace Recharts with ECharts `line` series.
  Color from `--brand-accent` (this is an informational line, not an action, so brass
  is acceptable as a chart series line — but flag in review if it looks wrong).

- [ ] **Add `SkeletonChart` composite** (deferred from Phase 4L):
  Add to `frontend/src/shared/design-system/components/Skeleton.tsx`.
  Renders a full-width `Skeleton` block with shimmer (matches ECharts container size).

- [ ] **Remove Recharts:**
  ```powershell
  cd frontend
  pnpm remove recharts
  ```
  Confirm no `from 'recharts'` imports remain: `grep -r "from 'recharts'" src/`.

- [ ] **Verify:** `pnpm test:run` all green. `pnpm typecheck` clean.
  Bundle: `pnpm build` succeeds; confirm `echarts` chunk is lazy (not in main bundle).
- [ ] **Commit:** `feat: phase 4M task 10 -- §V.2 ECharts migration; remove Recharts`

---

## Task 11: Phase 4L cleanup — Toast deletion, SkeletonCameraTree, SkeletonTimeline

**Goal:** Complete the Phase 4L deferred cleanup: delete the old `Toast.tsx` /
`ToastProvider` (now superseded by Sonner `VmsToaster`), and add the last two
missing skeleton composites (`SkeletonTimeline`, `SkeletonCameraTree`).

**Current state from Phase 4L notes:**
- `frontend/src/shared/design-system/components/Toast.tsx` still exists
- `frontend/src/shared/design-system/components/Toast.test.tsx` still exists
- `frontend/src/shared/design-system/components/primitives.a11y.test.tsx` imports `ToastProvider`
- `@radix-ui/react-toast` still in `package.json`

- [ ] **Audit Toast callers:**
  Run `grep -r "from.*Toast\|ToastProvider\|useToast" frontend/src/ --include="*.tsx" --include="*.ts"`.
  List every caller. Migrate any remaining call sites to `vmsToast.*` from `VmsToaster`.

- [ ] **Delete Toast files:**
  - `frontend/src/shared/design-system/components/Toast.tsx`
  - `frontend/src/shared/design-system/components/Toast.test.tsx`

- [ ] **Fix `primitives.a11y.test.tsx`:** remove `ToastProvider` import + usage;
  replace with a bare render (the a11y test validates aria patterns, not Toast specifically).

- [ ] **Remove `@radix-ui/react-toast`:**
  ```powershell
  cd frontend; pnpm remove @radix-ui/react-toast
  ```

- [ ] **Add `SkeletonTimeline`** to `Skeleton.tsx`:
  Full-width bar with 8 evenly spaced mark skeletons (matches `AlertTimeline` from Task 6).

- [ ] **Add `SkeletonCameraTree`** to `Skeleton.tsx`:
  3 group-header skeletons + 4 camera-row skeletons with a status dot circle + name bar.

- [ ] **Update `Skeleton.test.tsx`**: add tests for `SkeletonTimeline` and `SkeletonCameraTree`.

- [ ] **Verify:** `pnpm test:run` all green. `pnpm typecheck` clean.
  `grep -r "ToastProvider\|from.*Toast'" frontend/src/` returns zero.
- [ ] **Commit:** `feat: phase 4M task 11 -- delete old Toast, add SkeletonTimeline + SkeletonCameraTree`

---

## Task 12: Phase wrap-up

- [ ] **Full quality gate:**
  ```powershell
  cd frontend
  pnpm lint          # 0 errors
  pnpm typecheck     # 0 errors
  pnpm test:run      # all pass; note final count
  node scripts/check-visual-restraint.mjs   # 0 violations
  pnpm build         # succeeds; ECharts lazy chunk confirmed
  ```

- [ ] **Python gate:**
  ```powershell
  black vms/ tests/; ruff check vms/ tests/; mypy vms/; pytest --cov=vms
  ```

- [ ] **Bundle budget check:**
  Report the size of the main JS chunk and the ECharts lazy chunk from `pnpm build`
  output. If main chunk > 300 kB gzip, flag for investigation.

- [ ] **§T gut-check:** open `/live` in the browser with a handful of cameras showing
  different statuses. Confirm the status badge variety does not make the grid look
  hue-heavy (§T visual restraint note). If it does, reduce badge size or defer detail
  to hover only — document the decision in implementation notes.

- [ ] **Update plan status:** `**Status: COMPLETE — <date>, <N> tests passing**`

- [ ] **Update CLAUDE.md §3:** mark Phase 4M as last major milestone; update Next section
  to Phase 5 (security: at-rest cipher, JWT hardening, audit-log immutability trigger,
  sensitive-log filter).

- [ ] **Write implementation notes:**
  `docs/superpowers/notes/2026-07-07-vms-phase4m-implementation-notes.md`

---

## Known risks and mitigations

| Risk | Mitigation |
|---|---|
| `DataTable` rewrite breaks `AdminPersonsPage` + `AuditLogViewerPage` | Task 4 preserves existing page tests as regression guards before the migration |
| `react-resizable-panels` v4 API differs from docs | Read package CHANGELOG before Task 6; pin exact version |
| ECharts SSR hydration in Vitest | Wrap `ReactECharts` in lazy + Suspense; mocks in test use `SkeletonChart` as the Suspense fallback |
| §Q 5-level tree: cameras with all-null hierarchy display flat | "Default Site/Building/Floor" grouping fallback; no crash |
| Recharts removal breaks analytics tests | Tests migrated to ECharts in Task 10 before removal; `pnpm remove recharts` is the last step |
| `@xyflow/react` absent (topology deferred) | NOT needed for Phase 4M — install with the topology feature in Phase 6c |
| `useWorkspacePrefs` Zustand version migration | `migrate` coerces unknown shape to defaults; never throws; covered by test |

---

## Deferred to Phase 5 / later

| Item | Reason |
|---|---|
| Topology screen (`@xyflow/react` consumer) | Phase 6c plan already written |
| Floor plan / map overlay (`leaflet` consumer) | No backend geometry data yet |
| §D inline edit + hover preview | Not in §D acceptance criteria; complex regression risk |
| 5-level tree with real site data | Requires cameras table to have populated `site_name`/`building_name`/`floor_name` (operators must fill via camera edit form) |
| `adaface_min_sim` re-calibration | Mandatory `/advisor` — blocked on real footage |

---

**End of Phase 4M plan.**
