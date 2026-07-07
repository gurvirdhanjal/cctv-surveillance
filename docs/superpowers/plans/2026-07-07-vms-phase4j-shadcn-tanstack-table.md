# Phase 4J — shadcn/ui + TanStack Table Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use the `frontend-design` skill at the start of each implementation task to get aesthetic guidance for any new component being built. Run `pnpm lint && pnpm typecheck && pnpm test:run` after every task.

**Status: NOT STARTED**

**Goal:** Close the confirmed component-library gap. Bring shadcn/ui into the codebase in "custom CSS" mode behind a compat layer that maps shadcn CSS variables to VMS design tokens (never the reverse), install the missing Radix primitives, add scope-limited Framer Motion, and rebuild all 6 admin data tables on TanStack Table via one shared `DataTable` wrapper. Also deliver the Command Palette (Cmd+K), a slide-from-right Sheet, Switch, Checkbox, and Collapsible. No visual token may be introduced that is not already defined in the design system §6.1.

**Architecture:** shadcn primitives live under `frontend/src/shared/design-system/components/ui/` (the "shadcn-derived primitives" location referenced in the frontend spec file-layout comment). VMS-branded wrappers stay in `frontend/src/shared/design-system/components/`. shadcn's generated CSS variables are declared once in `index.css` inside a `@layer base` compat block whose values are `var(--vms-*)` references — shadcn never gets its own literal colors and never overrides a VMS token. Framer Motion is added only to four call-sites (sidebar, modal, command palette, tab indicator) and is explicitly banned everywhere else. TanStack Table is wrapped by a single generic `DataTable<TData, TValue>` that renders exclusively with VMS table classes.

**Tech Stack:** React 18 + TypeScript, Tailwind 3.4, shadcn/ui (custom-CSS mode), Radix UI (Dialog, Select, Tabs, Toast, Tooltip already installed; adding DropdownMenu, Popover, Checkbox, Switch, Collapsible, ScrollArea, Separator), `@tanstack/react-table` v8, `@tanstack/react-virtual` v3 (already present), `framer-motion`, `cmdk` (or `@radix-ui` Command via shadcn), Zustand 4, TanStack Query v5, Vitest + Testing Library.

**Spec refs:**
- `docs/frontend/2026-05-01-vms-frontend-spec.md` §2 (tech stack — shadcn/ui), §6 (TopBar / Cmd+K), §18 (testing)
- `docs/frontend/2026-06-24-vms-design-system.md` §6.1 (token list — binding), §7 (component patterns), §7.6 (collapsible alert group), §9 (motion durations), §13 (a11y)
- `docs/superpowers/specs/2026-07-06-vms-enterprise-interaction-guidelines.md` §7.2 (command palette)

**Binding design-system rules for this phase (do not violate):**
- `brand-500 = #c0392b`: ONLY nav active left-bar (3px) + logo. NEVER on buttons/tables/palette.
- `action-700 = #1e293b`: ALL primary buttons, focus rings, toggle "on" state.
- `severity-critical = #dc2626`: ONLY severity badges/borders/fault indicators.
- Cards `rounded-xl`, buttons `rounded-[10px]`, badges `rounded-full`.
- Table header row: `text-[11px] font-semibold uppercase tracking-[0.06em] bg-surface-sunken h-9`.
- Mono data register: every ID/hash/timestamp/FPS uses `font-mono text-[13px]`.
- Motion: hover 100ms, dropdown 120ms, modal 180ms, toast 200ms. Never animate telemetry.
- No CSS var outside design-system §6.1. shadcn vars map INTO VMS vars, never override them.

---

## Task 0 — Dependency install

**Files changed:** `frontend/package.json`, `frontend/pnpm-lock.yaml`

**Steps:**
- [ ] Add exact deps (pinned, no `^` drift beyond lockfile):
  ```
  pnpm add @tanstack/react-table@^8
  pnpm add framer-motion@^11
  pnpm add cmdk@^1
  pnpm add @radix-ui/react-dropdown-menu @radix-ui/react-popover @radix-ui/react-checkbox @radix-ui/react-switch @radix-ui/react-collapsible @radix-ui/react-scroll-area @radix-ui/react-separator
  ```
- [ ] Confirm `@tanstack/react-virtual` already present (used in Task 10).
- [ ] Record gzipped bundle baseline before any code lands: `pnpm build && pnpm dlx source-map-explorer dist/assets/*.js --html /tmp/bundle-baseline.html` (or existing bundle CI). Note the current main-chunk gzip size in the Phase 4J notes file.

**Verification:**
- [ ] `pnpm install` clean, no peer-dep warnings that block build.
- [ ] `pnpm build` succeeds (no code changes yet, so this is a lockfile sanity check).
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 1 — shadcn init + CSS compat layer

**Files changed:** `frontend/components.json` (new), `frontend/src/index.css`, `frontend/tailwind.config.ts`, `frontend/src/shared/design-system/components/ui/` (created empty), `frontend/src/lib/utils.ts` (or confirm existing `cn`).

**Key design decision — custom-CSS mode:** Run `pnpm dlx shadcn@latest init` and answer:
- Style: `new-york`
- Base color: `slate` (closest to VMS charcoal; we override anyway)
- CSS variables: `yes`
- Tailwind config path: `tailwind.config.ts`
- Components alias: `@/shared/design-system/components/ui`
- Utils alias: `@/lib/utils` (if a `cn` helper already exists at `@/shared/lib/cn`, point `components.json` `aliases.utils` at it instead and delete the generated one).

The init will try to write a big `:root { --background: ...; }` block into `index.css`. **Do NOT accept shadcn's literal HSL values.** Immediately replace the generated block with the compat layer below.

**TDD steps:**
- [ ] Write `frontend/src/index.compat.test.ts` (a Vitest test that imports the compiled CSS is impractical; instead assert token integrity via a JS map). Create `frontend/src/shared/design-system/shadcn-compat.ts` exporting a frozen record of shadcn-var → vms-var strings, and test that (a) every shadcn var used by installed primitives is present, (b) no entry maps to a literal color (each value must start with `var(--`). Confirm test RED (module absent).
- [ ] Implement `shadcn-compat.ts` and the `index.css` `@layer base` block, then confirm GREEN.

**Full compat CSS to write into `index.css`** (place after the existing VMS `:root` token block, inside `@layer base`; light values shown, dark values reference the VMS dark tokens that already exist for the operator console):

```css
@layer base {
  /* shadcn compatibility layer.
     shadcn primitives reference these generic names; each one is a pointer
     into a VMS design-system token. Never assign a literal color here.
     VMS tokens (--surface-base, --action-700, etc.) are defined above and win. */
  :root {
    --background: var(--surface-base);          /* #ffffff */
    --foreground: var(--text-primary);
    --card: var(--surface-base);
    --card-foreground: var(--text-primary);
    --popover: var(--surface-base);
    --popover-foreground: var(--text-primary);
    --muted: var(--surface-sunken);             /* #f1f5f9 */
    --muted-foreground: var(--text-muted);
    --accent: var(--surface-raised);            /* #f8fafc */
    --accent-foreground: var(--text-primary);
    --border: var(--border-default);
    --input: var(--border-default);
    --ring: var(--action-700);                  /* focus ring = charcoal, NOT crimson */
    --primary: var(--action-700);               /* buttons = charcoal */
    --primary-foreground: var(--action-50);
    --secondary: var(--surface-sunken);
    --secondary-foreground: var(--text-primary);
    --destructive: var(--severity-critical);    /* #dc2626 — severity only */
    --destructive-foreground: #ffffff;
    --radius: 0.625rem;                          /* 10px — matches button radius */
  }

  .dark {
    --background: var(--surface-base-dark);
    --foreground: var(--text-primary-dark);
    --card: var(--surface-raised-dark);
    --card-foreground: var(--text-primary-dark);
    --popover: var(--surface-raised-dark);
    --popover-foreground: var(--text-primary-dark);
    --muted: var(--surface-sunken-dark);
    --muted-foreground: var(--text-muted-dark);
    --accent: var(--surface-raised-dark);
    --accent-foreground: var(--text-primary-dark);
    --border: var(--border-default-dark);
    --input: var(--border-default-dark);
    --ring: var(--action-500);
    --primary: var(--action-600);
    --primary-foreground: var(--action-50);
    --secondary: var(--surface-sunken-dark);
    --secondary-foreground: var(--text-primary-dark);
    --destructive: var(--severity-critical);
    --destructive-foreground: #ffffff;
  }
}
```

- [ ] If any `--surface-*-dark` / `--text-*-dark` / `--border-default-dark` / `--action-*` var referenced above is not yet in the VMS §6.1 list, STOP — do not invent it. Either use the existing scoped `.theme-dark` selector that the sidebar/live view uses, or raise the missing-token question before proceeding (mandatory: no token outside §6.1).
- [ ] Ensure `tailwind.config.ts` keeps VMS token colors as the source of truth. shadcn init may append `colors: { background: 'hsl(var(--background))', ... }` — keep only what installed primitives require and do NOT let it shadow existing `brand`, `action`, `surface`, `severity`, `text`, `border` scales.
- [ ] Confirm `cn()` helper resolves (either generated `@/lib/utils` or the pre-existing one) and is used by all `ui/` primitives.

**Verification:**
- [ ] Grep confirms zero literal hex/hsl values inside the compat `@layer base` block (`rg -n "#[0-9a-fA-F]{3,6}|hsl\(" src/index.css` shows only the two `#ffffff` destructive-foreground lines).
- [ ] `shadcn-compat.test.ts` GREEN.
- [ ] App renders unchanged in light mode (visual check: no color regressions on `/admin`).
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 2 — Missing Radix primitives (shadcn-wrapped)

**Files changed (new, under `ui/`):** `DropdownMenu.tsx`, `Popover.tsx`, `Collapsible.tsx`, `ScrollArea.tsx`, `Separator.tsx`, `Switch.tsx`, `Checkbox.tsx` — plus one shared test `ui/primitives.test.tsx`.

**Key design decisions:**
- Generate each via `pnpm dlx shadcn@latest add dropdown-menu popover collapsible scroll-area separator switch checkbox`, then hand-edit generated classNames to VMS tokens:
  - `Switch` on-state track: `data-[state=checked]:bg-action-700` (charcoal, NOT crimson). Off-state: `bg-surface-sunken`. Thumb: `bg-white`. Motion: `transition-transform duration-100`.
  - `Checkbox` checked: `data-[state=checked]:bg-action-700 data-[state=checked]:border-action-700`, focus `focus-visible:ring-2 focus-visible:ring-action-700`, `rounded-[4px]`.
  - `DropdownMenu` content: `rounded-xl border border-border bg-surface-base shadow-lg`, item hover `focus:bg-surface-sunken`, animation `duration-[120ms]` (dropdown token). Radix `data-[state=open]/closed` for enter/exit.
  - `Popover` content: same surface/radius as dropdown, `duration-[120ms]`.
  - `Collapsible`: no color; uses `data-[state=open]` for height. Content uses `overflow-hidden`.
  - `ScrollArea` thumb: `bg-border rounded-full`.
  - `Separator`: `bg-border`.

**TDD steps:**
- [ ] Write `ui/primitives.test.tsx`: render each primitive open/checked; assert the checked/on element carries an `action-700` class (`bg-action-700`) and NOT `bg-brand-500`; assert DropdownMenu content has `rounded-xl`. Confirm RED.
- [ ] Generate + retheme; confirm GREEN.
- [ ] Add these to `primitives.a11y.test.tsx` (existing) axe pass: Switch has accessible label, Checkbox has label association, DropdownMenu items are keyboard-navigable.

**Verification:**
- [ ] `rg -n "bg-brand-500" src/shared/design-system/components/ui` returns nothing.
- [ ] axe: no violations on the primitives story.
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 3 — Sheet (slide-from-right drawer)

**Files changed (new):** `ui/Sheet.tsx`, `ui/Sheet.test.tsx`. Wraps `@radix-ui/react-dialog` (already installed).

**Key design decisions:**
- `SheetContent` variants via `cva`: `side: 'right' | 'left' | 'bottom'`. Default `right`.
- Right variant classes: `fixed inset-y-0 right-0 z-50 h-full w-full max-w-md border-l border-border bg-surface-base shadow-2xl`.
- Enter/exit uses Radix `data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right duration-180` (modal token = 180ms).
- Overlay: `bg-black/40 backdrop-blur-[1px]` with `duration-180`.
- Header: `SheetTitle` (`text-lg font-semibold text-text-primary`), `SheetDescription` (`text-sm text-text-muted`). Close button top-right, `focus-visible:ring-2 focus-visible:ring-action-700`.

**TDD steps:**
- [ ] `Sheet.test.tsx`: open sheet via trigger, assert content in DOM with `right-0`; press Esc, assert closed; assert overlay click closes; assert focus is trapped (first focusable receives focus). Confirm RED.
- [ ] Implement; confirm GREEN.

**Verification:**
- [ ] Esc + overlay-click both close; focus returns to trigger on close.
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 4 — Command Palette (Cmd+K)

**Files changed (new):** `ui/Command.tsx` (cmdk wrapper), `frontend/src/features/command/CommandPalette.tsx`, `CommandPalette.test.tsx`, `frontend/src/features/command/useCommandPalette.ts` (Zustand slice or context for open state), and a hook edit to `TopBar.tsx` (wire the search box + Cmd+K listener).

**Spec refs:** frontend spec §6, enterprise interaction guidelines §7.2.

**Behavior (exact):**
- Opens on `Cmd+K` / `Ctrl+K` (global `keydown`, ignore when focus is in an input other than the palette), or by clicking the TopBar search field.
- Sections in order: **Persons** (debounced 250ms API search), **Cameras** (recent, from liveStore), **Admin pages** (static route list).
- Person search hits `GET /api/persons/search?q=` via TanStack Query with `enabled: query.length >= 2`, `keepPreviousData: true`. Debounce the query string, not the fetch.
- Selecting a person → navigate `/analytics/persons/:id`; if that person has a live `trackId` in liveStore → offer a secondary "Follow live" action navigating `/live/follow/:trackId`.
- Selecting a camera → `/live` focus that camera (set `focusedCameraId` in liveStore).
- Selecting an admin page → navigate its route.
- Closes on `Esc` or on selection.
- Enter/exit wrapped in `<AnimatePresence>` (height + opacity), but the Framer wiring itself lands in Task 5 — here use the CSS transition and leave a `// Framer AnimatePresence added in Task 5` seam, OR sequence Task 5 before wiring animation. (Decision: implement palette logic here with cmdk's built-in animation; upgrade to AnimatePresence in Task 5.)

**Design classes:**
- Dialog container: reuse `ui/Dialog` overlay; palette panel `w-full max-w-xl rounded-xl border border-border bg-surface-base shadow-2xl overflow-hidden`.
- Input row: `h-12 border-b border-border px-4 text-sm` with a leading `Search` lucide icon `text-text-muted`.
- Group heading: `text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted px-3 py-2`.
- Item: `flex items-center gap-3 rounded-[10px] px-3 py-2 text-sm aria-selected:bg-surface-sunken`.
- Person GID rendered `font-mono text-[13px] text-text-muted` (mono data register).
- Empty: "No results" `text-text-muted text-sm` centered.

**TDD steps:**
- [ ] `CommandPalette.test.tsx`: (a) `Cmd+K` opens it; (b) typing "jo" (≥2 chars) triggers mocked `/api/persons/search` and renders results; (c) Enter on a person navigates to `/analytics/persons/:id` (assert router mock); (d) Esc closes; (e) selecting a camera sets `focusedCameraId`. Confirm RED.
- [ ] Implement; confirm GREEN.
- [ ] a11y: dialog has `role="dialog" aria-label="Command menu"`; list uses cmdk's roving focus; assert axe pass.

**Verification:**
- [ ] Debounce verified (only one fetch after rapid typing — use fake timers).
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 5 — Framer Motion (scope-limited)

**Files changed:** `AdminLayout.tsx` (sidebar), `ui/Dialog.tsx` + `ui/Sheet.tsx` (AnimatePresence), `ui/Tabs.tsx` or `design-system/components/Tabs.tsx` (sliding indicator), `CommandPalette.tsx` (AnimatePresence upgrade). New test `frontend/src/shared/motion/motion.test.tsx`.

**Explicit scope — animate ONLY these four:**
1. **Sidebar collapse/expand** (`AdminLayout`): wrap the sidebar container in `motion.div` with `layout` + `transition={{ duration: 0.18, ease: 'easeInOut' }}`. The crimson 3px active left-bar indicator uses `layoutId="nav-active"` so it slides between items.
2. **Modals** (`Dialog`, `Sheet`): wrap content in `<AnimatePresence>`; `motion.div` `initial={{opacity:0, scale:0.98}} animate={{opacity:1, scale:1}} exit={{opacity:0, scale:0.98}} transition={{duration:0.18}}`.
3. **Command palette**: `<AnimatePresence>` on open; height/opacity, `duration: 0.12`.
4. **Tab indicator**: the active-tab underline in `Tabs` uses `motion.span` with `layoutId="tab-underline"`, `transition={{duration:0.12}}`. Underline color `bg-action-700`.

**Explicitly DO NOT animate with Framer:** card hover (stays CSS `transition duration-100`), toasts (Radix Toast + CSS 200ms), telemetry/GPU/headcount numbers (never), video, PersonDots, bounding boxes, snapshot refresh, table rows.

**Motion budget note:** respect `prefers-reduced-motion` — wrap Framer transitions with a `useReducedMotion()` guard that sets `duration: 0` when reduced.

**TDD steps:**
- [ ] `motion.test.tsx`: assert sidebar toggle mounts a `motion.div` (query by test id) and the active indicator carries `layoutId` (via a data-attr shim in test); assert `useReducedMotion` path yields duration 0 (mock the hook). Confirm RED.
- [ ] Implement across the four sites; confirm GREEN.
- [ ] Regression: existing `AdminLayout.test.tsx`, `Modal.test.tsx`, `Tabs.test.tsx` still pass.

**Verification:**
- [ ] `rg -n "framer-motion" src` shows imports ONLY in the four allowed files + `useReducedMotion` helper.
- [ ] Reduced-motion honored.
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 6 — DataTable wrapper (shared, generic)

**Files changed (new):** `frontend/src/shared/design-system/components/DataTable.tsx`, `DataTable.test.tsx`, and supporting `DataTableColumnHeader.tsx` (sortable header), `DataTableToolbar.tsx` (search + column-visibility), `DataTablePagination.tsx`.

**API:**
```ts
interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  isLoading?: boolean;
  globalFilterPlaceholder?: string;
  enableRowSelection?: boolean;
  onRowSelectionChange?: (rows: TData[]) => void;   // for bulk actions
  pageSizeOptions?: number[];                        // default [10, 25, 50]
  emptyState?: React.ReactNode;                      // uses EmptyState component
}
```

**Features (all required):**
- Sorting on every column (`getSortedRowModel`), header click toggles asc/desc/none; sort icon via lucide `ChevronUp/Down/ChevronsUpDown` in `text-text-muted`.
- Global search filter (`getFilteredRowModel` + `globalFilter` state), debounced 200ms, input in toolbar `h-9 rounded-[10px] border border-border`.
- Column visibility toggle: `DropdownMenu` (Task 2) listing hideable columns with `Checkbox` items; button labeled "Columns" with `SlidersHorizontal` icon.
- Pagination (`getPaginationRowModel`): page size `Select` (10/25/50), prev/next buttons (`disabled` at bounds), "Showing X–Y of Z" `font-mono text-[13px]`.
- Row selection: leading checkbox column when `enableRowSelection`; header checkbox = select-all-on-page; emits selected rows for bulk actions.
- Sticky header: `<thead>` `sticky top-0 z-10`.
- Loading: when `isLoading`, render `Skeleton` rows (reuse Phase 4I `Skeleton`), not a spinner.

**Design classes (VMS, not shadcn defaults):**
- Wrapper: `rounded-xl border border-border bg-surface-base overflow-hidden`.
- `<thead>` row: `bg-surface-sunken`.
- `<th>`: `h-9 px-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted text-left`.
- `<td>`: `px-3 py-2.5 text-sm text-text-primary border-t border-border`.
- Row hover: `hover:bg-surface-sunken`.
- Selected row: `data-[state=selected]:bg-surface-sunken`.

**TDD steps:**
- [ ] `DataTable.test.tsx`: (a) renders rows from data; (b) clicking a sortable header reorders (assert first cell text); (c) typing in global search filters rows; (d) toggling a column in the Columns dropdown hides its cells; (e) changing page size re-renders count; (f) selecting header checkbox selects all page rows and fires `onRowSelectionChange`; (g) `isLoading` renders Skeleton rows; (h) empty data renders `emptyState`. Confirm RED.
- [ ] Implement; confirm GREEN.

**Verification:**
- [ ] No `bg-brand-500` / crimson anywhere in DataTable.
- [ ] Header sticky verified (scroll container test or manual).
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 7 — Cameras table (AdminCamerasPage)

**Files changed:** `AdminCamerasPage.tsx`, `AdminCamerasPage.test.tsx`, new `frontend/src/features/admin/tables/cameraColumns.tsx`.

**Columns:** select | Name | Camera ID (`font-mono text-[13px]`) | Status (`CameraStatusBadge`) | Tier badge | Zone | FPS (`font-mono`) | Last event (relative, `date-fns`) | actions (row DropdownMenu: Edit → CameraDetail, Recalibrate required, Delete).
**Bulk actions** (from row selection): "Mark recalibrate required" (calls `POST /api/cameras/{id}/recalibrate-required` per selected row), "Disable".
**Sorting:** all columns except actions. **Default sort:** Status (faults first).

**TDD steps:**
- [ ] Test: table renders camera rows from mocked `/api/cameras`; sort by Name works; row action "Edit" navigates to `/admin/cameras/:id`; bulk "recalibrate" fires the mocked endpoint for selected rows. Confirm RED → implement → GREEN.

**Verification:**
- [ ] Status column uses `CameraStatusBadge` (not raw text).
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 8 — Persons table (AdminPersonsPage)

**Files changed:** `AdminPersonsPage.tsx`, `AdminPersonsPage.test.tsx`, `tables/personColumns.tsx`.

**Columns:** select | thumbnail (small avatar) | Name | GID (`font-mono text-[13px]`) | Role/label | Embeddings count | Enrolled (date) | actions (Edit, Purge — GDPR).
**Purge action:** opens a confirm `Dialog` requiring typed full-name match + reason (per CLAUDE.md §7.3); admin-gated via `hasPermission(user.role,'persons','delete')`. Do NOT inline `role === 'admin'`.
**Global search:** matches name + GID.

**TDD steps:**
- [ ] Test: renders persons; GID column mono; Purge button hidden for non-admin (`hasPermission` mock false); Purge dialog requires exact name before submit enabled. Confirm RED → implement → GREEN.

**Verification:**
- [ ] Purge confirmation cannot submit without name match + reason.
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 9 — Users table (AdminUsersPage)

**Files changed:** `AdminUsersPage.tsx`, `AdminUsersPage.test.tsx`, `tables/userColumns.tsx`.

**Columns:** select | Name/email | Role badge | Camera-permission count | Last login (`font-mono` timestamp) | Active (`Switch`) | actions (Edit permissions → Sheet, Deactivate).
**Row Switch** toggles active state via `PATCH /api/users/{id}` (charcoal on-state). Edit permissions opens a `Sheet` (Task 3) with a camera checklist (`Checkbox` list, ScrollArea).

**TDD steps:**
- [ ] Test: renders users; toggling active Switch fires mocked PATCH; Edit opens Sheet with camera list. Confirm RED → implement → GREEN.

**Verification:**
- [ ] Switch on-state is `action-700`, never crimson.
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 10 — Audit log table (AuditLogViewerPage — virtualized, append-only)

**Files changed:** `AuditLogViewerPage.tsx`, `AuditLogViewerPage.test.tsx`, `tables/auditColumns.tsx`.

**Special constraints:** append-only (no row actions that mutate), potentially large row count → integrate **TanStack Virtual** inside the DataTable body (row virtualization). No row selection, no delete. Pagination is server-side cursor OR virtual scroll of a large fetched window — use virtual scroll over the page's fetched rows.

**Columns:** Timestamp (`font-mono text-[13px]`) | Event type (badge) | Actor | Target | Row hash (`font-mono`, truncated with copy-on-click) | Prev hash (`font-mono`, truncated).
**Chain integrity banner:** at top, "Verify chain" button hits `GET /api/audit/verify`; result shown as `severity` badge (verified = neutral/positive, broken = `severity-critical`). Export button → `GET /api/audit/export` (PDF download).

**Design decision:** DataTable gains an optional `virtualized?: boolean` + `estimateRowHeight` prop; when set, the `<tbody>` uses `useVirtualizer` with a scroll container of fixed height (`max-h-[70vh] overflow-auto`) and sticky header preserved. Guard: virtualization is opt-in so the other 5 tables are unaffected.

**TDD steps:**
- [ ] Test: renders audit rows; row hash column mono + copy button copies value (clipboard mock); "Verify chain" calls mocked `/api/audit/verify` and shows a badge; no row-mutation actions present; with 500 mocked rows only a subset of DOM rows rendered (virtualization). Confirm RED → implement → GREEN.

**Verification:**
- [ ] No mutate actions; hash columns mono; virtualization active for large sets.
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 11 — Alert routing table (AlertRoutingPage)

**Files changed:** `AlertRoutingPage.tsx`, `AlertRoutingPage.test.tsx`, `tables/alertRoutingColumns.tsx`.

**Columns:** select | Rule name | Alert type | Channel (email/slack/telegram/webhook) | Target | Enabled (`Switch`) | actions (Edit → Sheet/Dialog, Delete).
**Enabled Switch** → `PATCH /api/alert-routing/{id}`. Edit opens a form (React Hook Form + Zod) in a Sheet.

**TDD steps:**
- [ ] Test: renders rules; toggling Enabled fires mocked PATCH; Edit opens form Sheet with existing values. Confirm RED → implement → GREEN.

**Verification:**
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 12 — Anomaly detectors table (AnomalyDetectorsPage)

**Files changed:** `AnomalyDetectorsPage.tsx`, `AnomalyDetectorsPage.test.tsx`, `tables/anomalyColumns.tsx`.

**Columns:** Detector type | Scope (camera/zone) | Enabled (`Switch`) | Config summary | Last triggered (`font-mono`) | actions (Edit config → Sheet, view triggers).
**Enabled Switch** → `PATCH /api/anomaly-detectors/{id}`. Config edit opens a Sheet with a typed form (thresholds bound to backend config; numeric inputs, no hard-coded defaults — read from API).

**TDD steps:**
- [ ] Test: renders detectors; toggling Enabled fires mocked PATCH; Edit opens config Sheet. Confirm RED → implement → GREEN.

**Verification:**
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 13 — Quality gate + bundle check

**Files changed:** possibly `vite.config`/bundle CI config, Phase 4J notes.

**Steps:**
- [ ] Full suite green: `pnpm test:run` (expect prior 489 + new tests).
- [ ] `pnpm lint && pnpm typecheck` clean.
- [ ] `pnpm build`; verify main-chunk gzip ≤ **800 kB**. Framer (~96KB gz) + TanStack Table (~15KB gz) + cmdk (~8KB gz) are the expected increase; confirm we stayed under budget. If over, lazy-load the Command palette and DataTable-heavy admin routes via `React.lazy`.
- [ ] Confirm no `bg-brand-500` on any button/table/palette across changed files: `rg -n "bg-brand-500" src/features/admin src/features/command src/shared/design-system/components/ui`.
- [ ] Confirm shadcn compat layer intact (Task 1 grep).
- [ ] Update `docs/superpowers/notes/2026-07-07-vms-phase4j-implementation-notes.md` with bundle delta + decisions.
- [ ] Update CLAUDE.md §3 (mark Phase 4J complete, set next phase = 4K).
- [ ] Run quality gate: `pnpm lint && pnpm typecheck && pnpm test:run`

---

## Dependency notes for the executing agent
- Task 1 must land before every later task (compat layer underpins all shadcn primitives).
- Task 2 primitives (DropdownMenu, Checkbox, Switch) are consumed by Task 6 (DataTable toolbar/selection) and Tasks 9/11/12 (Switch).
- Task 3 (Sheet) is consumed by Tasks 8/9/11/12 (edit drawers).
- Task 4 (Command palette) is consumed by Phase 4K TopBar — do not skip.
- Task 6 (DataTable) blocks Tasks 7–12.
- Framer (Task 5) can run any time after Task 3/4 exist but before final quality gate.
