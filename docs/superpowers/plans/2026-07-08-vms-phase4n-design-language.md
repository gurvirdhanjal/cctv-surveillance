# Phase 4N — Design Language & Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: NOT STARTED**

**Goal:** Eliminate all design-language debt found in the 2026-07-08 audit: hardcoded
colors and palette creep, typography fragmentation, three-way theme scoping, the
oversized shadcn sidebar, the parallel alert cards, and the camera tree/tile mismatch.
After this phase, feature code contains zero hex literals, zero Tailwind palette classes,
zero arbitrary pixel font sizes — enforced by CI.

**Architecture:** Pure frontend. Token additions to `index.css` + `tailwind.config.ts`;
new `AppSidebar` and `CameraRow` components in the design system; merge of
`AlertCard`/`AlarmCard`; deletion of the shadcn sidebar stack and `useRouteTheme`. CI
enforcement extends the existing `check-visual-restraint` script.

**Tech Stack:** React 18 + TypeScript + Vite, Tailwind (token-mapped), Framer Motion,
Zustand (`useWorkspacePrefs`), Vitest + Testing Library.

**Spec refs:** `2026-07-08-vms-frontend-premium-polish.md` Parts I–II + §12;
`docs/frontend/2026-06-24-vms-design-system.md` §3.1, §6.1, §6.4 (amended by this phase);
`docs/frontend/2026-05-01-vms-frontend-spec.md`.

**Frontend gate (every task):** `cd frontend && pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 1 — Surface/overlay token additions

- [ ] Test first: extend `src/shared/design-system/tokens.test.ts` to assert
      `--surface-card`, `--surface-chip`, `--overlay-tile` are defined in BOTH
      `[data-theme='light']` and `[data-theme='dark']` blocks of `index.css`. Run → fails.
- [ ] Add tokens per spec §4.1: light `--surface-card:#ffffff`, `--surface-chip:#e2e8f0`,
      `--overlay-tile:rgba(15,23,42,0.05)`; dark `--surface-card:#1a2234`,
      `--surface-chip:#232d42`, `--overlay-tile:rgba(0,0,0,0.30)`.
- [ ] Map in `tailwind.config.ts` colors: `surface-card`, `surface-chip` →
      `var(--surface-*)` (direct var, no HSL wrapping — house style).
- [ ] Amend `docs/frontend/2026-06-24-vms-design-system.md` §6.1 token table with the
      three tokens and their intent (card = tile/alarm surfaces; chip = badges/inset
      pills/SLA track; overlay-tile = tile header scrim).
- [ ] Verify: token test passes; gate green.

## Task 2 — Typography scale registered in Tailwind

- [ ] Open design system §3.1; register the full type scale in `tailwind.config.ts`
      `fontSize` under the doc's canonical names (e.g. `label-xs: 11px`, `body-sm: 13px`,
      `body-md: 14px`, `body-lg: 16px`, `display-md: 24px`, `display-xl` — use the doc's
      exact names/values/line-heights; do not invent).
- [ ] Test: tokens.test.ts (or a new `typography.test.ts`) asserts the config exposes
      exactly the documented names.
- [ ] Verify: `text-body-sm` etc. compile in a scratch component; gate green.

## Task 3 — CI gate: hex/palette/pixel-size bans

- [ ] Test first: extend `src/shared/design-system/__tests__/check-visual-restraint.test.ts`
      with cases: a feature file containing `#1a2234` fails; `text-slate-400` fails;
      `bg-black/30` fails; `text-[13px]` fails; the same strings inside
      `src/shared/design-system/` token definitions pass; `var(--severity-critical)`
      inside an arbitrary-value class passes. Run → fails.
- [ ] Extend the restraint script: scan `src/features/**/*.tsx` for
      (a) hex literals `#[0-9a-fA-F]{3,8}` outside `var(...)` fallbacks,
      (b) palette classes `(text|bg|border|ring|fill|stroke)-(slate|gray|zinc|neutral|stone|amber|red|orange|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]`,
      plus `text-white`, `bg-black`,
      (c) `text-\[\d+px\]`.
      Report file:line per violation. Exit non-zero if any.
- [ ] Run the gate; capture the violation inventory as the worklist for Tasks 4–5.
      DO NOT mark this task done until Tasks 4–5 make the gate green (gate lands in the
      same phase it starts failing — CI stays green at phase end, red mid-phase is fine
      locally but do not push mid-phase).
- [ ] Verify: unit tests for the script pass.

## Task 4 — Detokenize the live feature (worklist from Task 3)

Mapping (spec §4.1): `#0a0e1a→bg-surface-base`, `#111827→bg-surface-raised`,
`#1a2234→bg-surface-card`, `#232d42→bg-surface-chip`, `#1e293b/#1f2937→border`,
`#334155→border-strong`, `text-slate-100/200→text-text-primary`,
`text-slate-300/400→text-text-secondary`, `text-slate-500/600→text-text-muted`,
`text-white→text-text-inverse`, `bg-black/30→bg-[var(--overlay-tile)]`,
`bg-amber-400→bg-[var(--status-auth-failed)]`, `#22c55e→bg-[var(--status-online)]`.

- [ ] `LivePage.tsx` (lines ~72, 91, 97, 102, 108, 117) — panel/border/base surfaces.
- [ ] `CameraTile.tsx` — tier badge map, status dot map, card bg, header scrim, body text.
- [ ] `AlarmCard.tsx` — card bg, all slate text, SLA track (`bg-surface-chip`).
- [ ] `CameraTree.tsx` — search input, tree labels, pager, borders.
- [ ] Sweep remaining live components the Task 3 inventory flags (`TopBar`,
      `SystemStatusStrip`, `AlertSidebar`, `AlertTimeline`, `FocusedCamera`,
      `BoundingBoxOverlay`, `OfflineReconnectBanner`, `ShortcutLegend`, `GridLayoutSelector`).
- [ ] Update tests asserting old literal classNames (e.g. CameraTile/CameraTree
      `border-[var(--severity-critical)]` stays; any `#1a2234`-style assertions move to
      token classes).
- [ ] Verify: restraint gate reports zero hex/palette violations in `src/features/live/`;
      visual smoke in dark theme (`pnpm dev`, /live) — no color shifts beyond the
      `#1e293b→#1f2937` border unification; gate green.

## Task 5 — Typography migration (worklist from Task 3)

- [ ] Replace all `text-[Xpx]` in `src/features/` and `src/shared/` per the spec §4.2
      mapping (9px/10px/11px→`label-xs`; 12px/13px→`body-sm`; 14px/15px→`body-md`;
      18px/20px/22px→`display-md` for page titles, `body-lg` for section heads — judge
      per usage, note judgments in implementation notes).
- [ ] Add `font-mono tabular-nums` to every numeric readout touched (SLA seconds, pager
      counts, timestamps already `font-mono` — add `tabular-nums`).
- [ ] Update tests asserting `text-[Xpx]` strings.
- [ ] Verify: restraint gate fully green (Tasks 3–5 close together); gate green.

## Task 6 — Focus-ring standardization

- [ ] Create `src/shared/design-system/focus.ts` exporting `focusRing` (the spec §4.3
      recipe) with a unit test asserting it contains `focus-visible:` and no bare `focus:`.
- [ ] `ForensicSearchPage.tsx`: replace `focus:ring-*` with `focusRing`; replace the 4 raw
      `<input>`s with design-system `Input` and the submit `<button>` with `Button`.
- [ ] Adopt `focusRing` in components with hand-rolled rings (AlertCard/AlarmCard CTAs,
      CameraTree pager/search — as touched in Task 4, fold in here if simpler).
- [ ] Verify: `grep -rn "focus:ring\|focus:outline" src/features/` → empty; a11y tests pass.

## Task 7 — Theme-scoping standard

- [ ] Delete `src/hooks/useRouteTheme.ts`; `grep -rn "useRouteTheme" src/` → empty.
- [ ] Confirm scoped `data-theme` on layout roots: AdminLayout (`light`, done 2026-07-08),
      LivePage (`dark`), ForensicSearchPage/AnalyticsLayout (`light`) — normalize any
      stragglers to the same pattern.
- [ ] Error pages (`NotFoundPage`, `ForbiddenPage`): assert root uses `bg-surface-base`
      + `text-text-primary` (theme-following, no override); add/adjust test.
- [ ] Amend design system §6.4: scoped-attribute is the standard; hook removed.
- [ ] Verify: toggle dark in ProfileDialog while on /admin → zero flicker, admin stays
      light, /live stays dark, error pages follow preference; gate green.

## Task 8 — AppSidebar (minimal, replaces shadcn)

- [ ] Test first: new `AppSidebar.test.tsx` — renders `<aside>` with `aria-label` from
      props; nav groups + items from config; active item has `bg-surface-sunken` and the
      brass `[border-left:3px_solid_var(--brand-accent)]`; collapsed state (from
      `useWorkspacePrefs.sidebarCollapsed`) hides labels and sets 56px width class;
      Ctrl+B toggles; footer slot renders. Run → fails.
- [ ] Implement `src/shared/design-system/components/AppSidebar.tsx` (~120 lines):
      props `{ ariaLabel, header, sections: {group, items: {to, label, icon, end}[]}[],
      footer }`; NavLink items with `layoutId` active spring (reuse current AdminLayout
      markup); design-system Tooltip for collapsed labels; `useReducedMotion` gates.
- [ ] Add `sidebarCollapsed: boolean` + setter to `useWorkspacePrefs` (persisted) + test.
- [ ] Migrate `AdminLayout.tsx` to AppSidebar; keep `<nav aria-label="Admin navigation">`,
      page-transition wrapper, ProfileDialog, header bar. AdminLayout tests pass unchanged
      (update only imports/structure-agnostic queries if strictly required).
- [ ] Delete: `ui/sidebar.tsx`, `ui/button.tsx`, `ui/input.tsx`, `ui/skeleton.tsx`,
      `ui/tooltip.tsx`, `src/shared/hooks/use-mobile.tsx`. `grep -rn "ui/sidebar\|ui/button\|ui/skeleton\|use-mobile" src/` → empty.
      Remove now-orphaned deps from package.json if any (`pnpm why` each radix package
      the deleted files imported; remove only truly orphaned ones).
- [ ] Verify: gate green; bundle size noted in implementation notes (expect shrink).

## Task 9 — Shell unification (Analytics + Forensic)

- [ ] `AnalyticsLayout.tsx` adopts AppSidebar with its nav config (Dashboard, Timeline,
      Heatmap; Forensic link moves into a nav group). Keep page transitions.
- [ ] Forensic route nests under the Analytics shell (router change in
      `src/app/routes.tsx`); `ForensicSearchPage` drops its standalone full-screen wrapper
      and `data-theme` (inherited from the shell).
- [ ] Update AnalyticsLayout/Forensic tests (nav landmark, route render).
- [ ] Error pages: minimal centered shell (logo mark + message + CTA home) — shared
      `ErrorShell` if both pages duplicate markup.
- [ ] Verify: /forensic shows analytics nav; deep-link works; gate green.

## Task 10 — Alert card unification

- [ ] Test first: merge `AlertCard.test.tsx` + `AlarmCard.test.tsx` into one suite for
      the unified `AlertCard`: severity border-l token, SLA bar (tiers ok/warn/crit →
      `bg-border`/`bg-[var(--severity-medium)]`/`bg-[var(--severity-critical)]`),
      similar-alerts collapsible, all four optional handlers show/hide buttons, `isNew`
      flash class, `isSelected` ring, non-OPEN state hides actions. Run → fails.
- [ ] Implement unified `AlertCard.tsx`: AlarmCard's features + AlertCard's tokens +
      `isNew`; design-system `Button` for actions; `bg-surface-card`; `useCountdown` SLA.
- [ ] Migrate consumers (`AlertSidebar`, any AlarmCard imports); delete `AlarmCard.tsx`
      + its test file; `grep -rn "AlarmCard" src/` → empty.
- [ ] Verify: alerts.a11y tests pass; gate green.

## Task 11 — CameraRow + CameraTree refactor

- [ ] Test first: `CameraRow.test.tsx` — 28px row renders status dot (pulse class when
      alarming), truncated name with `title`, tier chip `bg-surface-chip`, REC dot when
      recording, `aria-pressed` when focused, onSelect fires. Run → fails.
- [ ] Implement `CameraRow.tsx` (live components) per spec §5.4 — tokens only.
- [ ] `CameraTree.tsx`: replace tile grids with `CameraRow` lists (hierarchy, dnd-kit
      reorder, Virtuoso >200, search all preserved); remove the 12-tile pagination from
      the tree (rows are cheap — paginate only if >200 via Virtuoso); keep Escape-to-focused
      behavior against the row list.
- [ ] Wire `GridLayoutSelector` to a `liveStore` view mode: `focused` (default,
      FocusedCamera) ↔ `grid` (CameraTile multi-up grid in the center panel using the
      existing tile + selected grid dims). CameraTile itself: tokens already fixed (Task 4).
- [ ] Empty state: EmptyState "No cameras yet" + role-gated "Add cameras" CTA →
      `/admin/cameras` (uses `hasPermission(user.role, 'cameras', 'create')`).
- [ ] Update CameraTree tests (row-based queries, alarm class on row); add grid-mode test.
- [ ] Verify: tree renders 52-camera fixture without overflow at 280px panel width
      (assert no horizontal scroll in test via clientWidth/scrollWidth); gate green.

## Task 12 — Phase close-out

- [ ] Full gate: `pnpm lint && pnpm typecheck && pnpm test:run` green; coverage ≥80%
      shared / ≥70% features (`pnpm test:run -- --coverage`).
- [ ] Restraint gate green: zero hex, zero palette classes, zero `text-[Xpx]` in features.
- [ ] Deletions confirmed: shadcn sidebar stack, `useRouteTheme`, `AlarmCard`.
- [ ] Update spec §3 problem inventory rows to "FIXED (4N)"; update CLAUDE.md §3
      milestone line; write `docs/superpowers/notes/2026-07-08-vms-phase4n-implementation-notes.md`.
- [ ] Conventional commits throughout (one logical change each); plan Status → COMPLETE.
