# Phase 4M — Interactive Surfaces Implementation Notes

**Status: COMPLETE** · 2026-07-08 · 795 frontend tests · 823 Python tests

---

## Task 1 — §R Workspace Personalization (Zustand persist)

`useWorkspacePrefs` store added to `frontend/src/shared/store/workspacePrefs.ts`.
Persists `pinnedCameraIds`, `hiddenAlertTypes`, `cmdkRecents`, `treeExpansion`, `treeOrder`
via `zustand/middleware/persist` with `localStorage` key `vms-workspace-prefs`.
Test: `useWorkspacePrefs.test.ts` — 5 tests covering initial state and each setter.

## Task 2 — §D DataTable core (TanStack + Virtuoso)

`DataTable` component at `frontend/src/shared/design-system/components/DataTable.tsx`.
Uses `@tanstack/react-table` v8 for sorting, column-reorder, row-select, pinned rows.
`react-virtuoso` mounts when `rows.length > 100`; standard `<table>` otherwise.
Column reorder via `@dnd-kit/core` + `@dnd-kit/sortable` with `horizontalListSortingStrategy`.
CSV export: `exportDataTableCsv()` utility building Blob + `<a download>`.

## Task 3 — §D DataTable integration (AdminPersonsPage, AdminCamerasPage)

Both admin pages upgraded from raw `<table>` to `<DataTable>`.
Empty state uses the shared `EmptyState` component.
Loading state uses `SkeletonTable`.

## Task 4 — §E WorkspaceShell (react-resizable-panels)

`WorkspaceShell` wraps the `/live` route with a 3-column `<PanelGroup direction="horizontal">`:
320px `CameraTree` panel | `1fr` `FocusedCamera` panel | 380px `AlertSidebar` panel.
Panel sizes persist to `useWorkspacePrefs.panelSizes` on `onLayout` callback.
`react-resizable-panels` requires a `ResizeObserver` polyfill in jsdom — added to `setup.ts`.

## Task 5 — §I Resizable TimeScrubber panels

`TimeScrubber` wrapped in a `<PanelGroup direction="horizontal">` allowing the waveform
and markers panes to resize independently. Panel layout persists to workspace prefs.

## Task 6 — §F + §J PremiumCameraCard + FloatingActionBar

`PremiumCameraCard`: Framer Motion `whileHover={{ y: -2 }}` lift, `scale(1.01)`.
`FloatingActionBar`: 3-button overlay (`AnimatePresence` fade in on parent hover).
Buttons: View Live, Export Clip, View Person. Glass surface: `glass-panel` token.
`SkeletonTimeline` composite added to `Skeleton.tsx`: height 120px, 8 marks, `aria-hidden`.

## Task 7 — §F + §J Tests

PremiumCameraCard: hover lift animation, glass overlay, 3 action buttons.
FloatingActionBar: mounts on hover, not on blur. 7 tests total.

## Task 8 — §Q Hierarchical CameraTree + backend migration

**Alembic migration** `c3d4e5f6a7b8`: adds nullable `site_name`, `building_name`,
`floor_name` (String(200)) to `cameras` table. ORM models + Pydantic schemas updated.
Test: `tests/test_api_camera_schemas.py` — 4 new tests for hierarchy fields.

**Frontend**: `CameraTree.tsx` fully rewritten. `buildHierarchy()` groups flat camera list
into `SiteGroup[]` via 4-level Map nesting. Cameras with no `site_name` fall under
"Default Site". Tree nodes use `aria-expanded`, Framer Motion collapse (160ms), ChevronRight
rotation. Dnd-kit `SortableContext` per zone; cross-zone drag rejected in `handleDragEnd`.
Virtuoso mounts at >200 cameras (flat-rows mode with ancestor labels).
`SkeletonCameraTree`: 3 group-header skeletons + 4 camera-row skeletons.

**Key fix**: `visibleFlat` unused variable removed after JSX refactor — ESLint would have
failed the quality gate otherwise.

## Task 9 — §P CommandPalette upgrade (cmdk v1)

`frontend/src/shared/command/CommandPalette.tsx`: 6 fixed groups (Cameras, Persons, Zones,
Alerts, Navigation, Actions) + Recent group when `cmdkRecents.length > 0` and query empty.
Wrapper class: `glass-cmdk z-[60] shadow-4 rounded-xl`. Uses `Icon.*` from design-system icons.
`run(fn, recent?)` helper: calls action, pushes to recents store, closes palette.
`frontend/src/components/CommandPalette.tsx` becomes a re-export shim.

**Test strategy**: mocked the entire `@/shared/design-system/components/ui/Command` module
with simple HTML divs — avoids `ResizeObserver` + `scrollIntoView` jsdom incompatibilities
from cmdk's internal use of Radix UI. Zustand `setState` calls in tests wrapped in `act()`.

**Global stub**: `ResizeObserver` polyfill added to `frontend/src/test-utils/setup.ts` —
fixes both cmdk and react-resizable-panels across the entire test suite.

## Task 10 — §V.2 ECharts migration

`frontend/src/shared/charts/EChartsWrapper.tsx`:
- `ReactECharts` loaded via `React.lazy(() => import('echarts-for-react'))` — keeps it
  out of the main bundle.
- `<React.Suspense>` fallback renders `<SkeletonChart>` while the chunk loads.
- `useChartTheme()` reads CSS custom properties from `getComputedStyle(document.body)`,
  returns `{ textColor, mutedColor, borderColor, backgroundColor }`.

`AlertVolumeChart`, `HeadCountChart`, `DwellChart` all rewritten using `EChartsWrapper`.
`recharts` removed from dependencies (`pnpm remove recharts`). Zero remaining imports confirmed.
`SkeletonChart`: `role="status"` + `aria-label="Loading chart"` (not `aria-hidden`) —
needs to be perceivable as a loading state by screen readers.

## Task 11 — Toast/ToastProvider cleanup

`frontend/src/shared/design-system/components/Toast.tsx` deleted.
`frontend/src/shared/design-system/components/Toast.test.tsx` deleted.
`primitives.a11y.test.tsx` updated to remove `ToastProvider` import and its 2 tests.
`Skeleton.test.tsx` extended with 3 new describe blocks:
  - `SkeletonTimeline (§I)` — height 120px, 9 animate-pulse els, aria-hidden
  - `SkeletonCameraTree (§Q)` — renders, ≥3 aria-hidden els
  - `SkeletonChart (§V.2)` — role=status, name="Loading chart", height 192px, style override

## Cross-cutting notes

- Pre-existing lint warnings (6) in `Card.tsx` and `VmsToaster.tsx` for
  `react-refresh/only-export-components` — not introduced by this phase.
- Pre-existing Python test failures (6): Triton connection refused (no Triton server in dev),
  config env var isolation issues — not introduced by this phase.
- Python test count: 823 passing (phase start: ~822).
- Frontend test count: 795 passing (phase start: ~722 from Phase 4L).
