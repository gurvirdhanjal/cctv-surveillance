# Phase 4H — Admin Enterprise Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE**

**Goal:** Bring all remaining admin pages from "functional but unstyled / partially styled" to enterprise-ready quality matching the design system. Completes the Phase 4G remaining tasks (4G.2–4G.7) and closes the Phase 4 completion checklist.

**Architecture:** Pure frontend polish pass — no new API endpoints, no schema changes, no new routes. All pages already have correct logic, queries, and mutations. This plan only touches: className strings (token substitutions), empty-state components, modal rounding, input rounding, color token fixes, and label typography.

**Tech Stack:** React 18 + TypeScript, Tailwind CSS 3.4, design-system tokens (CSS custom properties), Vitest + RTL (existing tests remain green — no logic changes)

**Spec refs:**
- `docs/frontend/2026-06-24-vms-design-system.md` §14 (enterprise design principles — binding rulebook)
- `docs/frontend/2026-05-01-vms-frontend-spec.md` §9 (admin views spec)
- `docs/superpowers/plans/2026-06-24-vms-phase4-frontend.md` (parent plan — 4G remaining tasks)

---

## Binding token cheat-sheet (apply everywhere in this phase)

Do not deviate. These are the only allowed values for the changes in this plan.

| Element | Token / class |
|---|---|
| Card container | `rounded-xl border border-border bg-surface-base shadow-[var(--shadow-1)]` (hover → `shadow-[var(--shadow-2)]`) |
| Button / input radius | `rounded-[10px]` |
| Badge radius | `rounded-full` |
| Modal / dialog radius | `rounded-xl` |
| Nav item radius | `rounded-lg` |
| Page title | `text-[22px] font-bold text-text-primary` |
| Section label | `text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted` |
| Card title | `text-[14px] font-semibold` |
| Body text | `text-[14px]` |
| Table body text | `text-[13px]` |
| Badge / meta text | `text-[11px]` |
| Input standard | `h-10 rounded-[10px] border border-border bg-surface-base px-3 focus:border-brand-500 focus:outline-none` |
| Button primary | `h-10 rounded-[10px] bg-brand-500 px-4 text-[13px] font-medium text-white hover:bg-brand-700` |
| Button secondary | `h-10 rounded-[10px] border border-border px-4 text-[13px] text-text-secondary hover:text-text-primary` |
| Success chrome | `text-success` / `bg-success/10` (never `bg-green-*` / `text-green-*`) |
| Error chrome | `text-error` / `bg-error/10` / subtle `bg-error/5` (never `bg-red-*`) |
| Warning chrome | `text-warning` / `bg-warning/10` / `border-warning/20` (never `bg-amber-*` / `bg-yellow-*`) |
| Info chrome | `text-info` / `bg-info/10` (never `bg-blue-*`) |
| Muted text | `text-text-muted` (never `text-gray-*` / `text-slate-*`) |
| Spacing | 8pt grid only — 4/8/16/24/32/48/64 px (t-1, t-2, t-4, t-6, t-8, t-12, t-16) |

**Forbidden token names (never use):** `surface-elevated`, `border-subtle`, `border-muted`, `text-tertiary`, `surface-hover`. See CLAUDE.md §5.1.

**Test convention:** Pure className/token changes require NO test edits (tests do not assert on class names). After each task run `pnpm test:run` (from `frontend/`) to confirm the page still renders green. Only add/adjust a test when a task introduces a NEW component (Task 1, Task 2).

---

## Section 1 — Shared utilities

Extract two reusable components so every page uses one implementation. Do these first; later tasks import them.

### Task 1 — `<EmptyState>` component

- [ ] Create `frontend/src/features/admin/components/EmptyState.tsx`
  - Props: `{ icon: LucideIcon; title: string; description?: string; action?: React.ReactNode }`
  - Renders the design-system empty-state pattern exactly:
    ```tsx
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface-base py-20 text-center">
      <Icon className="mb-4 h-10 w-10 text-text-muted opacity-30" aria-hidden />
      <p className="text-[15px] font-semibold text-text-secondary">{title}</p>
      {description && <p className="mt-1 text-[13px] text-text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
    ```
- [ ] Create `frontend/src/features/admin/components/EmptyState.test.tsx`
  - Positive: renders `title`, `description`, and a passed `action` node
  - Negative: omits `description`/`action` paragraphs when props absent
- [ ] Verify: `pnpm test:run src/features/admin/components/EmptyState.test.tsx`

### Task 2 — `<StatusBadge5State>` component

- [ ] Create `frontend/src/features/admin/components/StatusBadge5State.tsx`
  - Prop: `status: 'online' | 'offline' | 'maintenance' | 'auth_failed' | 'critical'`
  - Map to design-system 5-state badge (§14 status tokens), each `rounded-full` `text-[11px]` with icon + label:
    - `online` → `bg-success/10 text-success`, pulsing dot (`animate-pulse`)
    - `offline` → `bg-surface-sunken text-text-muted`, gray dot
    - `maintenance` → `bg-info/10 text-info`, `Calendar` icon
    - `auth_failed` → `bg-warning/10 text-warning`, `KeyRound` icon
    - `critical` → `bg-error/10 text-error`, `AlertTriangle` icon
  - Reuse the existing `CameraStatusBadge` visual grammar from `AdminCamerasPage.tsx` (3-state) as the base; extend to 5 states. Do not modify `AdminCamerasPage.tsx` in this task.
- [ ] Create `frontend/src/features/admin/components/StatusBadge5State.test.tsx`
  - One assertion per state: correct label text renders for each of the 5 status values
- [ ] Verify: `pnpm test:run src/features/admin/components/StatusBadge5State.test.tsx`

---

## Section 2 — List pages

Each list page: swap card/badge/input radii to tokens, fix hardcoded colors, add page-header + section-label pattern from `AdminCamerasPage.tsx`, and wire in `<EmptyState>`.

### Task 3 — AdminPersonsPage redesign

- [ ] Edit `frontend/src/features/admin/AdminPersonsPage.tsx`
  - Person cards: `rounded` → `rounded-xl border border-border bg-surface-base shadow-[var(--shadow-1)]`
  - Badges: apply `rounded-full text-[11px]`; replace any hardcoded badge colors with status tokens (`bg-info/10 text-info`, etc.)
  - Add page-header pattern (`text-[22px] font-bold` title + primary "Add Person" button `rounded-[10px] bg-brand-500`)
  - Add section label above the list (`text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted`)
  - Empty state: import `<EmptyState icon={Users} title="No persons enrolled" description="Enrol a person to build the identity gallery." />`
  - Inputs (search/filter): apply the input standard class
- [ ] Verify: `pnpm test:run src/features/admin/AdminPersonsPage.test.tsx` (render must stay green; no test edit)

### Task 4 — AnomalyDetectorsPage redesign

- [ ] Edit `frontend/src/features/admin/AnomalyDetectorsPage.tsx`
  - Detector cards/rows: `rounded` → `rounded-xl` card treatment
  - Enable/disable toggle: add focus state `focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500` and correct on/off colors (`bg-brand-500` on, `bg-surface-sunken` off)
  - Section label + page title pattern
  - Empty state: `<EmptyState icon={ScanEye} title="No anomaly detectors configured" description="Detectors are registered by the anomaly framework." />` (choose an existing lucide icon already used in the bundle)
- [ ] Verify: `pnpm test:run src/features/admin/AnomalyDetectorsPage.test.tsx`

### Task 5 — AlertRoutingPage redesign

- [ ] Edit `frontend/src/features/admin/AlertRoutingPage.tsx`
  - Modal container: `rounded-lg` → `rounded-xl`
  - All modal inputs/selects: `rounded` → `rounded-[10px]`, apply input standard
  - Form labels: normalize to section-label typography (`text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted`)
  - Modal footer buttons: secondary Cancel + primary Save using the button standards
  - Empty state: `<EmptyState icon={BellRing} title="No alert routes" description="Add a route to dispatch alerts to email, Slack, Telegram, or webhook." />`
- [ ] Verify: `pnpm test:run src/features/admin/AlertRoutingPage.test.tsx`

### Task 6 — AuditLogViewerPage redesign

- [ ] Edit `frontend/src/features/admin/AuditLogViewerPage.tsx`
  - Verify-status chips: `bg-green-50 border-green-200` → `bg-success/10 text-success`; `bg-red-50 ...` → `bg-error/10 text-error`; `rounded-full text-[11px]`
  - Table: body text `text-[13px]`; container `rounded-xl border border-border`
  - Page title + section label pattern
  - Empty state: `<EmptyState icon={ScrollText} title="No audit events" description="Adjust filters or widen the date range." />`
- [ ] Verify: `pnpm test:run src/features/admin/AuditLogViewerPage.test.tsx`

### Task 7 — ZoneEditorPage redesign

- [ ] Edit `frontend/src/features/admin/ZoneEditorPage.tsx`
  - Modal container: `rounded-xl`; inputs: `rounded-[10px]` + input standard
  - Labels: section-label typography
  - Keep `bg-destructive text-white` on the delete-confirm button (already correct per design system)
  - Empty state (no zones defined): `<EmptyState icon={SquareDashed} title="No zones defined" description="Draw a zone on the camera view to begin." />`
- [ ] Verify: `pnpm test:run src/features/admin/ZoneEditorPage.test.tsx`

---

## Section 3 — Detail pages

### Task 8 — CameraDetailPage redesign

- [ ] Edit `frontend/src/features/admin/CameraDetailPage.tsx`
  - Keep the tab UI (already clean) — do not restructure it
  - Hardcoded error color → `text-error`
  - Card/panel containers: `rounded` → `rounded-xl border border-border shadow-[var(--shadow-1)]`
  - Header: page title `text-[22px] font-bold`; camera status via `<StatusBadge5State>` (Task 2) instead of any inline badge
- [ ] Verify: `pnpm test:run src/features/admin/CameraDetailPage.test.tsx`

### Task 9 — HardwareTab redesign

- [ ] Edit `frontend/src/features/admin/camera-tabs/HardwareTab.tsx`
  - Dialog: `rounded-xl`; dialog inputs: input standard
  - Field rows: label typography (`text-[11px]` section labels or `text-[13px]` field labels — match sibling tabs), value `text-[14px]`
  - Container: `rounded-xl border border-border`
- [ ] Verify: `pnpm test:run src/features/admin/camera-tabs/HardwareTab.test.tsx`

### Task 10 — OverridesTab redesign

- [ ] Edit `frontend/src/features/admin/camera-tabs/OverridesTab.tsx`
  - Warning banner: `bg-amber-50 border-amber-200` → `bg-warning/10 border border-warning/20 text-warning`, `rounded-[10px]`
  - Inputs: `rounded` → `rounded-[10px]` + input standard
  - Labels: field-label typography consistent with HardwareTab
- [ ] Verify: `pnpm test:run src/features/admin/camera-tabs/OverridesTab.test.tsx`

### Task 11 — HomographyCalibrator redesign

- [ ] Edit `frontend/src/features/admin/camera-tabs/HomographyCalibrator.tsx`
  - Success banner: `bg-green-50 border-green-200` → `bg-success/10 border border-success/20 text-success`
  - Error banner: `bg-red-50 ...` → `bg-error/10 border border-error/20 text-error`
  - Buttons: primary/secondary standards; radius `rounded-[10px]`
  - Container: `rounded-xl`
- [ ] Verify: `pnpm test:run src/features/admin/camera-tabs/HomographyCalibrator.test.tsx`

---

## Section 4 — Stub pages

API-blocked pages (P3 users, P4 models). Polish the placeholder only — do NOT add fake data or non-functional controls.

### Task 12 — AdminUsersPage stub polish

- [ ] Edit `frontend/src/features/admin/AdminUsersPage.tsx`
  - Page title `text-[22px] font-bold`
  - Replace bare "coming soon" text with `<EmptyState icon={UsersRound} title="User management coming soon" description="Blocked on the users API (Phase 4 pre-work P3)." />`
  - No fake table, no disabled buttons that imply functionality
- [ ] Verify: `pnpm test:run src/features/admin/AdminUsersPage.test.tsx`

### Task 13 — ModelManagerPage stub polish

- [ ] Edit `frontend/src/features/admin/ModelManagerPage.tsx`
  - Page title `text-[22px] font-bold`
  - `<EmptyState icon={Boxes} title="Model manager coming soon" description="Blocked on the model-registry API (Phase 4 pre-work P4)." />`
- [ ] Verify: `pnpm test:run src/features/admin/ModelManagerPage.test.tsx`

---

## Section 5 — Phase 4G remaining tasks

These close out the parent Phase 4 plan's deferred items. E2E specs run against the `e2e/docker-compose.yml` stack — write the spec files; do not run docker in this plan.

### Task 14 — 4G.2 Guard E2E spec

- [ ] Complete `frontend/e2e/guard.spec.ts`
  - Cover the Guard console happy path: login as guard fixture → live view loads → an alert row appears → acknowledge flow
  - Use `e2e/fixtures.ts` for credentials; assert on `role="..."` / accessible names, not CSS classes
  - Mark suite so it only runs under Playwright (`test:e2e`), not Vitest
- [ ] Verify: `pnpm exec playwright test e2e/guard.spec.ts --list` (lists specs without a running stack)

### Task 15 — 4G.3 Admin E2E spec

- [ ] Complete `frontend/e2e/admin.spec.ts`
  - Cover: admin login → navigate cameras → add camera modal opens and validates → persons list renders → audit log filter applies
  - Reuse fixtures; accessible-name selectors
- [ ] Verify: `pnpm exec playwright test e2e/admin.spec.ts --list`

### Task 16 — 4G.4 Forensic E2E spec

- [ ] Complete `frontend/e2e/forensic.spec.ts`
  - Cover: forensic search page loads → clip playback controls present → search-by-text shows the 501/disabled state gracefully (matches backend `GET /api/forensic/search` returning 501, per CLAUDE.md §3)
- [ ] Verify: `pnpm exec playwright test e2e/forensic.spec.ts --list`

### Task 17 — 4G.6 Bundle-size CI script

- [ ] Create `frontend/scripts/check-bundle-size.mjs`
  - Read Vite build output. Prefer `dist/.vite/manifest.json` (enable `build.manifest: true` in `vite.config.ts` if not already on) or glob `dist/assets/*.js`; gzip each with node `zlib.gzipSync` and compare
  - Assert: initial `index-*.js` ≤ 800 kB gzip; `ForensicSearchPage-*` chunk: warn > 300 kB gzip, FAIL > 400 kB gzip; exit non-zero on any hard failure with a per-chunk table printed to stdout
  - Current baseline (must pass): index 122.86 kB gzip, ForensicSearchPage 175.87 kB gzip
- [ ] Add `"check:bundle": "node scripts/check-bundle-size.mjs"` to `package.json` scripts
- [ ] Verify: `pnpm build && pnpm check:bundle` prints the table and exits 0

### Task 18 — 4G.7 Lighthouse CI documentation

- [ ] Add a short "Lighthouse CI" subsection to `docs/superpowers/notes/2026-06-24-vms-phase4-implementation-notes.md`
  - Document the canonical approach: Playwright launches the app → `lighthouse` (or `@lhci/cli`) runs against `preview` server → assert Performance/Accessibility budgets
  - State clearly it requires a running server (docker stack or `pnpm preview`) and is therefore DEFERRED to run until the stack is available; only the approach is committed now
  - No script execution in this task
- [ ] Verify: notes file contains the subsection (read-back check)

---

## Section 6 — Phase 4 wrap-up

### Task 19 — Full frontend quality gate

- [ ] From `frontend/`: run `pnpm lint`, `pnpm typecheck`, `pnpm test:run`
  - All green. Coverage: `src/shared/` ≥ 80%, `src/features/` ≥ 70% (CLAUDE.md §5.1)
  - Fix any lint/type regressions introduced by token swaps (unused imports from removed inline badges, etc.)
- [ ] Verify: three commands exit 0; coverage at/above targets

### Task 20 — Visual consistency pass

- [ ] Grep the redesigned files for forbidden patterns and confirm zero hits:
  - `bg-green-`, `bg-red-`, `bg-amber-`, `bg-yellow-`, `bg-blue-`, `text-green-`, `text-red-`, `text-gray-`, `text-slate-`
  - forbidden tokens: `surface-elevated`, `border-subtle`, `border-muted`, `text-tertiary`, `surface-hover`
  - stray `rounded-lg` on modals, stray bare `rounded` on cards/inputs
- [ ] Verify: `grep -rE "bg-(green|red|amber|yellow|blue)-|surface-elevated|border-subtle|text-tertiary|surface-hover" src/features/admin/` returns nothing

### Task 21 — Update plan statuses and CLAUDE.md §3

- [ ] Mark all checkboxes in this plan done; set this file's **Status: COMPLETE**
- [ ] In `docs/superpowers/plans/2026-06-24-vms-phase4-frontend.md`: mark 4G.2, 4G.3, 4G.4, 4G.6, 4G.7 done and the sub-plan 4H reference complete
- [ ] Update CLAUDE.md §3 "Active" line to reflect Phase 4 frontend complete; note Phase 5 security is next
- [ ] Verify: read-back — no unchecked 4G/4H boxes remain

### Task 22 — Implementation notes + commit

- [ ] Append a Phase 4H section to `docs/superpowers/notes/2026-06-24-vms-phase4-implementation-notes.md`: what was restyled, the two new shared components, the bundle script, and the deferred Lighthouse run
- [ ] Follow CLAUDE.md §9 commit protocol (safe-push): `git add -u` tracked changes only, conventional commit `feat: phase 4h -- admin enterprise redesign + 4G e2e/bundle closeout`, on the feature branch (never push to `main` without instruction)
- [ ] Verify: `git status` clean; report commit hash

---

## Notes for the executor

- All logic already works — if a test starts asserting on behavior you did not change, you touched more than className strings. Revert and re-scope.
- Do the two shared components (Tasks 1–2) FIRST; every list/detail task imports them.
- Keep each task to ≤ 2–3 files. If a page needs both a component swap and a new import site elsewhere, that is fine within the 2–3 file budget.
- Pick lucide icons that are already in the dependency graph where possible to avoid growing the bundle; the empty-state icons named above are illustrative — confirm the import exists or substitute a near-equivalent already used in `frontend/src`.
