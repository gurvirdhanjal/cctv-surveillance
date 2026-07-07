# Phase 4L — Enterprise UX Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE — 2026-07-07, 722 tests passing**

**Goal:** Elevate the VMS frontend from functional to cohesive enterprise-grade UX — tokens, motion, elevation, icon registry, primitives, status badges, skeletons, glass/blur, nav, micro-interactions, action bar, visual-restraint gates, and Sonner toasts.

**Architecture:** Pure frontend polish — no new backend routes, no domain data changes. Builds on Tailwind CSS, Radix UI, Framer Motion, TanStack Query, Zustand, React Hook Form + Zod stack. New packages: sonner, cmdk, @dnd-kit/core+sortable, react-resizable-panels, react-virtuoso, echarts + echarts-for-react.

**Tech Stack:** React 19, TypeScript, Tailwind CSS v3, Framer Motion, Radix UI, Zustand, TanStack Query v5, pnpm.

**Spec refs:** `docs/superpowers/specs/2026-07-07-vms-phase4l-enterprise-ux-polish.md`, `docs/frontend/2026-06-24-vms-design-system.md`, `docs/frontend/2026-05-01-vms-frontend-spec.md`

---

## Scope

This plan ships the 13 Phase 4L items from spec §W (foundations first, then polish):

| Task | Ref | Section | Risk |
|------|-----|---------|------|
| 1 | — | Install new packages | Foundation |
| 2 | §G | Complete Design Tokens | Foundation — must land first |
| 3 | §H | Motion Guidelines | Foundation |
| 4 | §C | Elevation Layers | Foundation |
| 5 | §B | Semantic Icon Language + icon sweep | Foundation |
| 6 | §A | Design Language primitives (Box/Stack/Cluster/Surface) | Medium |
| 7 | §A | Button variants + Card variants | Medium |
| 8 | §K | Rich Status Badge (13 states) | Low |
| 9 | §L | Skeleton States (6 types) | Low |
| 10 | §M | Subtle Glass + Blur (4 surfaces) | Low |
| 11 | §O | Micro Interactions | Medium |
| 12 | §N | Premium Navigation (validate/fix existing) | Low |
| 13 | §S | Unified Action Bar | Low |
| 14 | §T | Visual Restraint (lint/CI gates + tightening) | Low |
| 15 | §V.1 | Toasts → Sonner migration | Self-contained |

**Deferred to Phase 4M (NOT in this plan):** §D (Premium Tables), §E (Workspace Architecture), §I (Live View resizable refit), §F (Premium Camera Cards), §J (Floating Action Bars), §Q (Camera Tree), §P (Command Palette), §R (Workspace Personalization), §V.2 (Recharts → ECharts).

Note: packages `cmdk`, `@dnd-kit/*`, `react-resizable-panels`, `react-virtuoso`, `echarts`, `echarts-for-react` are installed in Task 1 but **consumed** by Phase 4M. Installing them now keeps the lockfile stable across both phases and lets Task 14's dependency-cruiser gate whitelist them upfront.

---

## Global rules (apply to every task)

- **TDD mandate.** Every task: write a failing test → run it, confirm it fails for the expected reason → implement the minimum → run it, confirm it passes → commit. Never write implementation before the failing test.
- **Quality gate before every commit** touching `frontend/`:
  ```powershell
  cd frontend
  pnpm lint
  pnpm typecheck
  pnpm test:run
  ```
  All three must pass. A task is not done until they do.
- **Three-tier color model (inviolable).**
  - Brand brass (`--brand-accent`) = logo + nav active indicator **only**. Never on focus rings, buttons, badges, or anything else.
  - Action charcoal (`--interactive-primary` / `action-*`) = all buttons, toggles, focus rings.
  - Alarm red `#dc2626` (`--destructive` / `severity-critical`) = severity only.
- **Token rule.** Never invent a Tailwind class name. Only tokens defined in the design-system §6.1 registry (as extended by §G / Task 2) may appear in classNames. New tokens must be added to `index.css` **and** `tailwind.config.ts` in the same task.
- **Commit format.** Conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `chore:`). One logical change per commit. No AI co-author footer.
- **Coverage.** `src/shared/` ≥ 80%, `src/features/` ≥ 70%.
- **Existing components — do not re-implement.** Button, Badge, EmptyState, Skeleton, CameraStatusBadge (12-state), PageHeader already exist under `frontend/src/shared/design-system/components/`. Extend, don't recreate.
- **`index.css` supersede rule.** §G / Task 2 **replaces** the existing `--shadow-1/2/3` values in `index.css` (lines 83–85 light, 134–136 dark) — it does not append duplicate shadow vars. The old `--duration-*` block (lines 28–36) is superseded by the §G `--dur-*` names; keep the old names as aliases only if a grep shows live consumers (see Task 3).

---

## Task 1 — Install new packages

**Files:** `frontend/package.json`, `frontend/pnpm-lock.yaml`

**Steps:**
- [ ] From `frontend/`, install runtime deps used in 4L and 4M:
  ```powershell
  cd frontend
  pnpm add sonner cmdk @dnd-kit/core @dnd-kit/sortable react-resizable-panels react-virtuoso echarts echarts-for-react
  ```
- [ ] Confirm each package resolves and `pnpm-lock.yaml` updates. Do **not** pin transitive versions manually.
- [ ] Write a smoke test `frontend/src/shared/design-system/__tests__/deps-4l.test.ts` that dynamically imports each new package and asserts a known export exists (e.g. `import { Toaster } from 'sonner'` → `expect(Toaster).toBeTruthy()`; `import { Command } from 'cmdk'`; `import { DndContext } from '@dnd-kit/core'`; `import { Panel } from 'react-resizable-panels'`; `import { Virtuoso } from 'react-virtuoso'`; `import ReactECharts from 'echarts-for-react'`).
- [ ] Run test → confirm it fails before install / passes after: `pnpm test:run -- deps-4l.test.ts`

**Verify:** `pnpm typecheck && pnpm test:run -- deps-4l.test.ts` clean.

**Commit:** `chore: add sonner, cmdk, @dnd-kit, react-resizable-panels, react-virtuoso, echarts frontend deps`

**Acceptance:** All six packages installed; import smoke test green; lockfile committed.

---

## Task 2 — §G Complete Design Tokens

**Files:** `frontend/src/index.css`, `frontend/tailwind.config.ts`, `frontend/src/shared/design-system/tokens.ts`, `frontend/src/shared/design-system/tokens.test.ts`

**Goal:** Add the full §G token set (radius, spacing, durations, four-tier shadows, interaction states) as CSS custom properties, expose them through Tailwind, and mirror in `tokens.ts`.

**Exact values to add:**
- Radius (theme-invariant `:root`):
  `--radius-xs:2px; --radius-sm:4px; --radius-md:6px; --radius-lg:8px; --radius-xl:12px; --radius-2xl:16px; --radius-full:9999px`
- Spacing scale (px, theme-invariant): `2,4,8,12,16,20,24,32,40,48,64,80,96`
- Animation durations (theme-invariant): `--dur-fast:80ms; --dur-normal:120ms; --dur-slow:180ms; --dur-xslow:300ms`
- Shadows **light** (replace existing `--shadow-1/2/3`, add `--shadow-4`):
  `--shadow-1: 0 1px 2px rgba(15,23,42,0.06); --shadow-2: 0 2px 6px rgba(15,23,42,0.10); --shadow-3: 0 8px 24px rgba(15,23,42,0.14); --shadow-4: 0 16px 48px rgba(15,23,42,0.20)`
- Shadows **dark** (replace existing, add `--shadow-4`):
  `--shadow-1: 0 1px 3px rgba(0,0,0,0.25); --shadow-2: 0 2px 8px rgba(0,0,0,0.40); --shadow-3: 0 8px 24px rgba(0,0,0,0.55); --shadow-4: 0 16px 48px rgba(0,0,0,0.65)`
- Interaction states (theme-invariant `:root`, using `#dc2626`-free values):
  `--state-focus-ring: 0 0 0 2px var(--surface-base), 0 0 0 4px var(--focus-ring)` (charcoal ring, NOT brass);
  `--state-selection: inset 0 0 0 2px var(--border-strong)`;
  `--state-hover-overlay: rgba(15,23,42,0.04)`;
  `--state-pressed-overlay: rgba(15,23,42,0.08)`

**Steps:**
- [ ] **Test first.** Extend `tokens.test.ts` with a block asserting the new token exports (see below) exist with exact values. Add a JSDOM/CSS-parse assertion: read `index.css` as text in the test and assert each new `--radius-*`, `--dur-*`, `--shadow-4`, and `--state-*` custom property string is present with its exact value. Run → confirm fails.
- [ ] In `index.css`, add a `/* ─── Radius ─── */` block in `:root` with the seven radius vars.
- [ ] Add a `/* ─── Durations (§G) ─── */` block with the four `--dur-*` vars.
- [ ] **Replace** the light-theme `--shadow-1/2/3` (lines 83–85) with the four §G light shadow values incl. `--shadow-4`.
- [ ] **Replace** the dark-theme `--shadow-1/2/3` (lines 134–136) with the four §G dark shadow values incl. `--shadow-4`.
- [ ] Add the four `--state-*` interaction vars in `:root` (theme-invariant). Confirm `--state-focus-ring` references `--focus-ring` (charcoal), never `--brand-accent`.
- [ ] In `tailwind.config.ts`: extend `borderRadius` with `xs:'var(--radius-xs)', 2xl:'var(--radius-2xl)', full:'var(--radius-full)'` (keep existing sm/md/lg/xl but repoint to the new vars); extend `boxShadow` with `4: 'var(--shadow-4)'`; extend `transitionDuration` with the four §G names `'dur-fast'|'dur-normal'|'dur-slow'|'dur-xslow'` → the `--dur-*` vars; extend `spacing` only if the spec §G scale differs from Tailwind defaults (it matches the default px steps, so document that no override is needed and add only the non-default `20` alias if missing — verify against Tailwind's default before adding).
- [ ] In `tokens.ts`: add `export const radius = { xs:'2px', sm:'4px', md:'6px', lg:'8px', xl:'12px', '2xl':'16px', full:'9999px' } as const`; add `export const durations = { fast:'80ms', normal:'120ms', slow:'180ms', xslow:'300ms' } as const`; extend `elevation` with `4` and repoint 1/2/3 to the §G light values; add `export const interactionStates` documenting the four `--state-*` var names (values are theme/CSS-var driven, so store the var reference strings).
- [ ] Run test → confirm passes.

**Verify:** `pnpm test:run -- tokens.test.ts` green; `pnpm typecheck` clean; grep confirms no duplicate `--shadow-1` declarations in `index.css`.

**Commit:** `feat: complete design token set — radius, durations, four-tier shadows, interaction states (§G)`

**Acceptance (spec §G checklist):** all radius/spacing/duration/shadow/state tokens present in CSS + Tailwind + tokens.ts; `--state-focus-ring` uses charcoal not brass; existing shadow vars replaced (no duplicates); tokens.ts mirrors CSS.

**Visual validation gate (dark theme shadows):** The spec pinned exact light-theme
rgba values but left dark as "black at higher alpha" with no exact numbers. This task
commits `rgba(0,0,0,0.25/0.40/0.55/0.65)` — a ~6–8× jump from the previous barely-
visible `0.024/0.04/0.08` values. Before merging Task 2 to main: open `/live` and
`/admin` in `[data-theme="dark"]`, check that raised cards, modal overlays, and the
live-view console look correct. Too-heavy shadows on dark surfaces can look like border
artifacts. Note result in implementation-notes (`docs/superpowers/notes/2026-07-07-vms-phase4l-implementation-notes.md`).

---

## Task 3 — §H Motion Guidelines

**Files:** new `frontend/src/shared/motion/motion.ts`, `frontend/src/shared/motion/motion.test.ts`

**Goal:** Single source of truth for Framer Motion transition presets. All animated components import from here — no inline magic durations.

**Exact values (seconds, for Framer `transition.duration`), all with `EASE = [0.4, 0, 0.2, 1]`:**
`hover:0.08, dropdown:0.12, popover:0.15, modal:0.18, sidebar:0.18, accordion:0.16, page:0.15, toast:0.20`

**Steps:**
- [ ] **Test first.** `motion.test.ts`: assert `EASE` equals `[0.4, 0, 0.2, 1]`; assert `MOTION.hover.duration === 0.08`, `MOTION.dropdown.duration === 0.12`, `MOTION.popover.duration === 0.15`, `MOTION.modal.duration === 0.18`, `MOTION.sidebar.duration === 0.18`, `MOTION.accordion.duration === 0.16`, `MOTION.page.duration === 0.15`, `MOTION.toast.duration === 0.20`; assert each preset carries `ease: EASE`. Run → fails.
- [ ] Implement `motion.ts`:
  ```ts
  export const EASE = [0.4, 0, 0.2, 1] as const
  const t = (duration: number) => ({ duration, ease: EASE })
  export const MOTION = {
    hover: t(0.08), dropdown: t(0.12), popover: t(0.15), modal: t(0.18),
    sidebar: t(0.18), accordion: t(0.16), page: t(0.15), toast: t(0.20),
  } as const
  ```
  Add a doc comment mapping each preset to its §H use.
- [ ] Add `export function reducedMotionSafe(transition)` helper returning `{ duration: 0 }` when `window.matchMedia('(prefers-reduced-motion: reduce)').matches` — components use this so motion is honored. Test the branch with a mocked `matchMedia`.
- [ ] Run test → passes.

**Verify:** `pnpm test:run -- motion.test.ts` green.

**Commit:** `feat: motion preset registry — §H durations + standard ease`

**Acceptance (spec §H checklist):** all eight presets exact; single EASE curve; reduced-motion helper present and tested. No component consumes these yet (Tasks 11/12 do).

---

## Task 4 — §C Elevation Layers

**Files:** new `frontend/src/shared/design-system/elevation.ts`, `frontend/src/shared/design-system/elevation.test.ts`

**Goal:** Codify the z-index ladder and the shadow-per-layer mapping so no component hard-codes a `z-[NN]`.

**Exact z-index ladder:**
`0-bg:0, 1-surface:0, 2-raised:1, 3-selected:2, 4-toolbar:40, 5-modal:50, 6-cmdk:60, 7-toast:70`

**Shadow mapping (per §C):** bg/surface → none; raised → shadow-1; selected → shadow-2; toolbar → shadow-2; modal → shadow-3; cmdk → shadow-3; toast → shadow-4.

**Steps:**
- [ ] **Test first.** `elevation.test.ts`: assert `Z.bg===0, Z.surface===0, Z.raised===1, Z.selected===2, Z.toolbar===40, Z.modal===50, Z.cmdk===60, Z.toast===70`; assert the shadow map returns the right `shadow-N` token key per layer. Run → fails.
- [ ] Implement `elevation.ts`: `export const Z = { bg:0, surface:0, raised:1, selected:2, toolbar:40, modal:50, cmdk:60, toast:70 } as const` and `export const ELEVATION_SHADOW: Record<keyof typeof Z, 0|1|2|3|4>` mapping to the shadow tier per the table above.
- [ ] Audit existing hard-coded z-index usages: `grep -rn "z-\[" frontend/src` and `grep -rn "zIndex" frontend/src`. For each hit in shared/modal/toast/toolbar surfaces, repoint to `Z.*` (e.g. Toast viewport `z-[100]` → `Z.toast`). Leave feature-local overlays that don't map to a ladder rung, but note them in the implementation notes.
- [ ] Extend `tailwind.config.ts` `zIndex` with named rungs (`raised:'1', selected:'2', toolbar:'40', modal:'50', cmdk:'60', toast:'70'`) so classNames can use `z-toast` etc.
- [ ] Run test → passes.

**Verify:** `pnpm test:run -- elevation.test.ts` green; `grep -rn "z-\[100\]"` in shared surfaces returns nothing.

**Commit:** `feat: elevation z-index ladder + shadow-per-layer map (§C)`

**Acceptance (spec §C checklist):** exact ladder; shadow mapping; shared modal/toast/toolbar surfaces use named rungs; no stray `z-[100]` in shared components.

---

## Task 5 — §B Semantic Icon Language + icon sweep

**Files:** new `frontend/src/shared/design-system/icons.tsx`, `frontend/src/shared/design-system/icons.test.tsx`, plus call-site edits across features (sweep).

**Goal:** Central icon registry mapping semantic names → `lucide-react` components. Every feature imports icons **by role name** from this registry, never `lucide-react` directly. Consistent size/stroke.

**Minimum registry set (36 names):**
`server, camera, recording, disconnected, analytics, storage, health, ai, map, playback, export, search, filter, add, edit, delete, bookmark, ptz, live, settings, user, users, zone, alert, audit, calendar, sync, calibrate, close, chevron-up, chevron-down, chevron-left, chevron-right, grid, list, pin`

**Steps:**
- [ ] **Test first.** `icons.test.tsx`: assert the registry exports a component for each of the 36 semantic names; assert rendering `<Icon name="camera" />` renders an svg; assert a default `size` (e.g. 16) and `strokeWidth` are applied; assert an invalid name is a TypeScript error (type-level — enforce via a `keyof` union). Run → fails.
- [ ] Implement `icons.tsx`: map each semantic name to a lucide component (e.g. `server: Server, camera: Video, recording: Circle/Disc, disconnected: WifiOff, analytics: BarChart3, ai: Sparkles, map: Map, playback: Play, export: Download, calibrate: Crosshair, pin: Pin`, etc.). Export `export type IconName = keyof typeof registry` and an `<Icon name size strokeWidth className />` wrapper applying `size=16`, `strokeWidth=1.75` defaults (confirm exact defaults against §B; if §B names them, use those).
- [ ] **Icon sweep.** `grep -rn "from 'lucide-react'" frontend/src` — for every direct lucide import in a **feature/page** file, replace with a semantic import from the registry where a registry name exists. Leave lucide imports only inside `icons.tsx` and any icon whose role isn't in the 36-set (note these in implementation notes as candidates to add to the registry). Keep edits surgical — swap the import + usage, don't restyle.
- [ ] After each batch of sweep edits, run `pnpm typecheck` to catch mismapped names.
- [ ] Run icon test → passes.

**Verify:** `pnpm test:run -- icons.test.tsx` green; `grep -rn "from 'lucide-react'"` returns only `icons.tsx` (plus any documented exceptions).

**Commit:** `feat: semantic icon registry + sweep feature call-sites to registry (§B)`

**Acceptance (spec §B checklist):** 36-name registry; consistent size/stroke defaults; feature files import by role name; typed `IconName` union; lucide direct imports isolated to registry.

---

## Task 6 — §A Design Language primitives (Box / Stack / Cluster / Surface)

**Files:** new `frontend/src/shared/design-system/primitives/{Box,Stack,Cluster,Surface}.tsx`, `frontend/src/shared/design-system/primitives/index.ts`, `frontend/src/shared/design-system/primitives/primitives.test.tsx`

**Goal:** Layout primitives that consume tokens so pages compose from a fixed vocabulary. All spacing props map to the §G spacing scale; `Surface` maps to elevation layers.

**Steps:**
- [ ] **Test first.** `primitives.test.tsx`:
  - `Box`: renders a `div`, forwards `className`, applies `p`/`px`/`py` props → spacing-scale classes.
  - `Stack`: `flex flex-col`, `gap` prop → gap-scale class, `align`/`justify` props.
  - `Cluster`: `flex flex-row flex-wrap`, `gap` prop, `align`/`justify`.
  - `Surface`: renders with `elevation` prop (`surface|raised|selected|modal`) → the correct `shadow-N` + `bg-surface-*` token classes from Task 4's map; renders `rounded-lg` by default; `as` prop for polymorphic element.
  - Assert each primitive forwards a `ref`.
  Run → fails.
- [ ] Implement the four primitives. Use `cn` from `@/shared/utils/cn`. `gap`/`p` props accept a spacing token key (e.g. `2|4|8|...`) and map to Tailwind spacing classes. `Surface.elevation` maps via `ELEVATION_SHADOW` from Task 4.
- [ ] Barrel-export from `primitives/index.ts`.
- [ ] Run test → passes. Run the existing `primitives.a11y.test.tsx` to confirm no regression (or extend it if it already covers primitives).

**Verify:** `pnpm test:run -- primitives.test.tsx` green; coverage on `primitives/` ≥ 80%.

**Commit:** `feat: layout primitives Box/Stack/Cluster/Surface consuming design tokens (§A)`

**Acceptance (spec §A primitives checklist):** four primitives; spacing props bound to §G scale; `Surface` bound to §C elevation; polymorphic `as`; ref forwarding; a11y test green.

---

## Task 7 — §A Button variants + Card variants

**Files:** `frontend/src/shared/design-system/components/Button.tsx`, `Button.test.tsx`, new `frontend/src/shared/design-system/components/Card.tsx`, `Card.test.tsx`

**Goal:** Extend the existing Button with the full §A variant set and add a Card component with variants. Buttons stay charcoal (action tier) — **never brass**.

**Steps:**
- [ ] **Read the existing `Button.tsx`** to see current variants before extending.
- [ ] **Test first (Button).** Extend `Button.test.tsx` to assert the §A variant set exists and renders the correct token classes: `primary` (charcoal `bg-[var(--interactive-primary)]`), `secondary` (surface + border), `ghost` (transparent, hover overlay), `destructive` (`bg-[var(--destructive)]`), `outline`. Assert sizes `sm|md|lg` map to §G radius + spacing. Assert focus ring uses `--state-focus-ring` (charcoal) not brass. Assert `disabled` uses disabled tokens. Run → fails for the missing variants.
- [ ] Implement missing Button variants/sizes. Reuse existing structure; add only what's missing. Keep the press micro-interaction hook point (Task 11 wires the `0.97` scale).
- [ ] **Test first (Card).** `Card.test.tsx`: `Card` renders a `Surface`-backed container with variants `default` (raised elevation), `interactive` (hover elevation bump + cursor), `outline` (border, no shadow); optional `CardHeader`/`CardBody`/`CardFooter` subcomponents render and forward className. Assert radius token `rounded-xl`. Run → fails.
- [ ] Implement `Card.tsx` composing `Surface` from Task 6. `interactive` variant adds hover elevation via className (motion added in Task 11).
- [ ] Run both tests → pass.

**Verify:** `pnpm test:run -- Button.test.tsx Card.test.tsx` green; grep confirms no `bg-brand` on any Button variant.

**Commit:** `feat: full Button variant set + Card component with variants (§A)`

**Acceptance (spec §A component checklist):** Button variants primary/secondary/ghost/destructive/outline + sizes sm/md/lg, charcoal-only, charcoal focus ring; Card default/interactive/outline + header/body/footer; both token-driven.

---

## Task 8 — §K Rich Status Badge (13 states)

**Files:** `frontend/src/shared/design-system/components/CameraStatusBadge.tsx`, `CameraStatusBadge.test.tsx`

**Goal:** Extend the existing 12-state `CameraStatusBadge` (Phase 4I) to the §K 13-state set. Add the one new state, verify icon + color + label for all 13. Severity stays alarm-red only; operational states use status tokens.

**Steps:**
- [ ] **Read the existing `CameraStatusBadge.tsx`** and its test to enumerate the current 12 states.
- [ ] **Cross-check spec §K** for the exact 13-state list, their labels, status-token color, and semantic icon (from Task 5 registry). Identify the one added state vs Phase 4I.
- [ ] **Test first.** Extend `CameraStatusBadge.test.tsx`: parametrized test over all 13 states asserting (a) correct label text, (b) correct status/severity token color class, (c) correct semantic icon name from the registry, (d) `role`/`aria-label` present. Add a test asserting an unknown state falls back safely. Run → fails on the 13th state.
- [ ] Implement: add the 13th state to the state map; migrate any inline lucide icons to Task 5 registry names; confirm colors use `status-*`/`severity-*` tokens (never brass).
- [ ] Run test → passes. Grep call-sites of `CameraStatusBadge` to confirm none pass a removed/renamed state.

**Verify:** `pnpm test:run -- CameraStatusBadge.test.tsx` green; coverage on the component ≥ 80%.

**Commit:** `feat: extend CameraStatusBadge to §K 13-state set with semantic icons`

**Acceptance (spec §K checklist):** 13 states, each with label + status/severity token color + semantic icon + aria; safe fallback; no brass.

---

## Task 9 — §L Skeleton States (6 types)

**Files:** `frontend/src/shared/design-system/components/Skeleton.tsx`, `Skeleton.test.tsx`

**Goal:** Extend the existing base `Skeleton` into the six §L composite types.

**Six types — spec §L names vs 4L scope:**

| §L spec name | 4L plan name | Rationale |
|---|---|---|
| `SkeletonKpiCard` | `SkeletonKpiCard` | ✓ spec name — use this |
| `SkeletonCameraCard` | `SkeletonCameraCard` | ✓ spec name — use this |
| `SkeletonTimeline` | deferred | Timeline is §I (Phase 4M); skip |
| `SkeletonTableRow` | `SkeletonTableRow` | ✓ spec name |
| `SkeletonChart` | deferred | Chart migration is §V.2 (Phase 4M); skip |
| `SkeletonCameraTree` | deferred | CameraTree is §Q (Phase 4M); skip |

Since §L's three remaining types target Phase 4M components, this task ships three
spec-anchored composites + supplements with two useful building-block skeletons:
`SkeletonText` (generic multi-line, no spec anchor — adds flexibility) and
`SkeletonAvatar` (no spec anchor — needed by Persons table). Note these two deviations
in the implementation-notes file.

**Steps:**
- [ ] **Read existing `Skeleton.tsx`** to reuse the base shimmer element.
- [ ] **Test first.** Extend `Skeleton.test.tsx`: for each of the six composites assert it renders, respects a `count`/`lines` prop where applicable, uses the base skeleton token (`bg-surface-sunken`/shimmer), and carries `aria-hidden` or `role="status"` + `aria-busy` per §13 a11y. Assert `prefers-reduced-motion` disables shimmer animation (test via class presence gated on media, or assert the animation class is the reduced-motion-safe one). Run → fails.
- [ ] Implement the six composites in `Skeleton.tsx` (or a `Skeleton/` folder if the file exceeds ~200 lines — keep under the 600-line rule). Reuse the base primitive; no new color tokens.
- [ ] Run test → passes.

**Verify:** `pnpm test:run -- Skeleton.test.tsx` green; coverage ≥ 80%.

**Commit:** `feat: six §L skeleton composites (text/card/table-row/avatar/stat/camera-tile)`

**Acceptance (spec §L checklist):** six composites; token-driven; a11y attributes; reduced-motion safe.

---

## Task 10 — §M Subtle Glass + Blur (4 surfaces)

**Files:** `frontend/src/index.css` (utility classes), affected surface components.

**Goal:** Add restrained glass/blur to the four §M-permitted surfaces. Blur is
**forbidden** on cards, modals, panels, and tables — this is a binding §M rule.

**The four permitted surfaces (per §M rule 1 — exact, no substitutions):**
Dropdown, Command Palette shell, Floating Toolbar, Context Menu.
Header/TopBar and modal/scrim are **NOT** in this list. §M explicitly calls out
"cards, modals, panels, tables must not blur." Task 10 applies blur only to the
four surfaces the spec names.

**Design note on dark shadow values (Task 2):** The §G spec pinned exact light-theme
shadow values but said dark uses "black at higher alpha" without exact numbers. Task 2
committed `rgba(0,0,0,0.25/0.40/0.55/0.65)` — a ~6–8× jump from the old
`0.024/0.04/0.08` values. This is likely correct (old values were barely visible on
near-black `#0a0e1a`), but it's a design decision made inside an implementation task.
**Visual validation required before merging:** check all raised surfaces, modal
overlays, and the live-view console in `[data-theme="dark"]` before calling Task 2
done. Note result in implementation-notes.

**Steps:**
- [ ] **Confirm the four target components in the live codebase.** Radix
  `DropdownMenu.Content` and `ContextMenu.Content` are the likely dropdown/context-menu
  primitives. CommandPalette shell is deferred to §P (Phase 4M) — but add the glass
  utility class now so it's ready. FloatingToolbar/ActionBar is Task 13.
- [ ] **Test first.** Add `frontend/src/shared/design-system/__tests__/glass.test.ts`
  asserting the four `glass-*` CSS utility classes exist in `index.css` with
  `backdrop-blur-md` (Tailwind `backdrop-filter: blur(12px)`) + `bg-surface-raised/95`
  alpha. Assert a `@media (prefers-reduced-transparency: reduce)` block removes the blur
  and uses opaque `bg-surface-raised`. Assert the modal/card component files do NOT
  contain `backdrop-blur` (CI guard). Run → fails.
- [ ] In `index.css`, add four utilities under `@layer utilities`:
  `.glass-dropdown`, `.glass-cmdk`, `.glass-toolbar`, `.glass-context-menu`.
  Each: `backdrop-blur-md; background-color: rgb(var(--surface-raised-rgb) / 0.95)` or
  the Tailwind equivalent. Add reduced-transparency fallback.
- [ ] Apply `.glass-dropdown` to `DropdownMenu.Content` and `.glass-context-menu` to
  `ContextMenu.Content` where those components exist. Do NOT apply blur to Modal,
  TopBar header, or any panel/card.
- [ ] Run test → passes.

**Verify:** `pnpm test:run -- glass.test.ts` green; visual sanity in dark theme; grep
confirms no `backdrop-blur` on Modal/Card components.

**Commit:** `feat: subtle glass/blur for dropdown/cmdk/toolbar/context-menu (§M)`

**Acceptance (spec §M checklist):** blur on the four spec-permitted surfaces only;
modal/card remain opaque; reduced-transparency fallback; matches spec `backdrop-blur-md bg-surface-raised/95`.

---

## Task 11 — §O Micro Interactions

**Files:** `frontend/src/shared/design-system/components/Button.tsx`, `frontend/src/shared/design-system/components/ui/Checkbox.tsx`, `Switch.tsx`, and their tests; consumes `MOTION` from Task 3.

**Goal:** Add the §O micro-interactions with **exact** spring/scale values, using Framer Motion, honoring reduced motion.

**Exact values:**
- Button press: `whileTap={{ scale: 0.97 }}` (exact — not 0.95/0.98), transition `MOTION.hover`.
- Checkbox check: spring `{ type: 'spring', stiffness: 500, damping: 30 }`.
- Toggle/Switch thumb: spring `{ type: 'spring', stiffness: 400, damping: 25 }`.

**Steps:**
- [ ] **Test first.**
  - `Button.test.tsx`: assert the button uses a Framer `motion` element with `whileTap` scale `0.97` (assert on the prop value passed, mocking framer-motion's `motion.button` to capture props). Assert reduced-motion disables the scale (via `reducedMotionSafe`).
  - `Checkbox.test.tsx`: assert the check indicator animates with spring `stiffness:500, damping:30`.
  - `Switch.test.tsx`: assert the thumb animates with spring `stiffness:400, damping:25`.
  Run → fails.
- [ ] Implement: wrap Button's root in `motion.button` (or `motion(Slot)` if `asChild` is used) with the tap scale; add the spring transitions to Checkbox indicator and Switch thumb. Import springs/durations from `motion.ts` where a preset exists; the spring configs are §O-specific constants — colocate them as named consts (`CHECKBOX_SPRING`, `TOGGLE_SPRING`) and export for testability.
- [ ] Ensure all three honor `prefers-reduced-motion` (scale/spring → instant).
- [ ] Run tests → pass.

**Verify:** `pnpm test:run -- Button.test.tsx Checkbox.test.tsx Switch.test.tsx` green.

**Commit:** `feat: micro-interactions — button press 0.97, checkbox/toggle springs (§O)`

**Acceptance (spec §O checklist):** button `0.97` exact; checkbox spring 500/30; toggle spring 400/25; reduced-motion honored on all.

---

## Task 12 — §N Premium Navigation (validate / fix existing)

**Files:** `frontend/src/features/admin/AdminLayout.tsx` (and any sidebar nav component it uses), its test.

**Goal:** Validate the existing Phase 4I animated nav (VmsLogo + Framer `layoutId` spring active indicator). Confirm it meets §N; fix only gaps. The active indicator is the **one sanctioned brass moment** — confirm it uses `--brand-accent`, and that nothing else in nav does.

**Steps:**
- [ ] **Read `AdminLayout.tsx`** and the nav item component; locate the `layoutId` active indicator.
- [ ] **Cross-check §N** requirements: active indicator animation (spring, `MOTION.sidebar` or the §N-specified spring), hover state (charcoal overlay, not brass), active item color, keyboard focus ring (charcoal), reduced-motion behavior, and that brass appears **only** on logo + active indicator.
- [ ] **Test first.** Extend the AdminLayout/nav test: assert the active nav item carries the `layoutId` indicator; assert the indicator color token is `--brand-accent`; assert hover state uses a charcoal/surface overlay (no `bg-brand`); assert the focus ring is charcoal; assert reduced-motion path. Run → identify which assertions fail (gaps).
- [ ] Fix only the failing gaps (repoint hover to `--state-hover-overlay`/surface token; ensure indicator uses `MOTION.sidebar` spring/duration; confirm brass isolation). If the existing nav already passes all assertions, the "implement" step is a no-op and the task documents that in the implementation notes.
- [ ] Run test → passes.

**Verify:** `pnpm test:run` on the nav test green; `grep -rn "brand" AdminLayout` shows brass only on logo + active indicator.

**Commit:** `fix: align premium navigation to §N — brass isolation, spring indicator, charcoal hover`

**Acceptance (spec §N checklist):** active indicator brass + spring; hover charcoal; focus charcoal; brass isolated to logo + active indicator; reduced-motion honored.

---

## Task 13 — §S Unified Action Bar

**Files:** new `frontend/src/shared/design-system/components/ActionBar.tsx`, `ActionBar.test.tsx`

**Goal:** A single reusable horizontal action bar (title/context slot + right-aligned action button cluster) that pages use for their top-of-page actions, replacing ad-hoc button rows. Uses `Cluster` primitive + `Button` variants + elevation `toolbar` + optional glass.

**Steps:**
- [ ] **Test first.** `ActionBar.test.tsx`: assert it renders a `left` slot (title/breadcrumb/context) and a `right` slot for actions; actions render in a `Cluster` with consistent gap (§G scale); assert it sits at elevation `toolbar` (uses `z-toolbar` + `shadow-2` per Task 4); assert optional `sticky` prop pins it (`sticky top-0`); assert primary action uses charcoal Button (no brass); assert `role="toolbar"` + `aria-label`. Run → fails.
- [ ] Implement `ActionBar.tsx` composing `Cluster`/`Surface` primitives (Tasks 6) and elevation tokens (Task 4). Optional `glass` prop applies `.glass-toolbar` (Task 10).
- [ ] **Do not** refactor every page to use it in this task (that's page-level polish under §T scope creep risk). Instead, adopt it in **one** representative page (e.g. `AdminCamerasPage.tsx` header actions) as the reference integration, and note remaining adoptions as follow-ups in implementation notes. Keep the edit surgical.
- [ ] Run test → passes; run the adopted page's test to confirm no regression.

**Verify:** `pnpm test:run -- ActionBar.test.tsx` green; coverage ≥ 80%.

**Commit:** `feat: unified ActionBar component + reference adoption (§S)`

**Acceptance (spec §S checklist):** left/right slots; Cluster action grouping; toolbar elevation; sticky option; charcoal primary; `role="toolbar"`; one reference page adopts it.

---

## Task 14 — §T Visual Restraint (lint/CI gates + tightening)

**Files:** `frontend/eslint.config.*` (or `.eslintrc`), new `frontend/scripts/check-visual-restraint.mjs` (or an ESLint rule config), `frontend/package.json` (script + CI hook), plus tightening edits to EmptyState / error surfaces.

**Goal:** Turn the three-tier color rule + token rule into an enforced gate, and tighten remaining EmptyState/error visuals per §T.

**Steps:**
- [ ] **Confirm §T's exact gate requirements** from the spec (which rules must be lint-enforced vs CI-scripted).
- [ ] **Test first.** Add `frontend/scripts/check-visual-restraint.test.mjs` (or a vitest) that runs the gate script against fixture strings: (a) a className containing `bg-brand-500` on a `<button>` → flagged; (b) an invented token `surface-elevated`/`border-subtle`/`text-tertiary`/`surface-hover` → flagged; (c) brass on a focus ring (`ring-brand`, `outline-brand`) → flagged; (d) legal usages (brass on logo/nav, charcoal button, red severity) → pass. Run → fails.
- [ ] Implement the gate as an ESLint rule config (`no-restricted-syntax` on className string patterns) **and/or** a standalone `check-visual-restraint.mjs` that greps `src/**/*.tsx` for the forbidden token names (the non-existent-token blocklist from CLAUDE.md §5.1: `surface-elevated`, `border-subtle`, `border-muted`, `text-tertiary`, `surface-hover`) and for `bg-brand`/`ring-brand`/`outline-brand` on interactive elements. Fail non-zero on any hit.
- [ ] Wire it into `package.json` (`"check:restraint": "node scripts/check-visual-restraint.mjs"`) and the existing lint/CI flow so it runs in the quality gate.
- [ ] **Run the gate against the whole `src/`** and fix every real violation it surfaces (repoint invented tokens to real ones per the §5.1 mapping; move any brass-on-button/focus to charcoal). This is the "tightening" work.
- [ ] Tighten EmptyState + error surfaces per §T: confirm they use `EmptyState`/error tokens, muted text, restrained iconography (single semantic icon, no decorative color). Edit only files the gate or §T flags.
- [ ] Run gate + tests → all green.

**Verify:** `node scripts/check-visual-restraint.mjs` exits 0 over `src/`; `pnpm test:run -- check-visual-restraint` green; `pnpm lint` clean.

**Commit:** `feat: visual-restraint CI gate + token/color tightening across src (§T)`

**Acceptance (spec §T checklist):** enforced gate for three-tier color + invented-token blocklist; gate wired into CI; zero live violations; EmptyState/error surfaces tightened.

---

## Task 15 — §V.1 Toasts → Sonner migration

**Files:** replace `frontend/src/shared/design-system/components/Toast.tsx` consumers with a Sonner-backed API; new `frontend/src/shared/design-system/components/toast.ts` (or `Toaster.tsx`), update `Toast.test.tsx` → `toast.test.tsx`, mount point in app root layout.

**Goal:** Migrate from the Radix-based `ToastProvider`/`ToastItem` to `sonner`, keeping a thin VMS wrapper so call-sites use `toast.success()/error()/warning()/info()` with our tokens + semantic icons. Preserve severity → color/icon mapping and a11y (`aria-live`).

**Steps:**
- [ ] **Find current toast call-sites.** `grep -rn "ToastProvider\|ToastItem\|onDismiss.*toast\|useToast" frontend/src` to enumerate consumers and the store/hook feeding `toasts`.
- [ ] **Test first.** `toast.test.tsx`:
  - assert the wrapper exports `toast.success/error/warning/info` and each calls `sonner`'s API with the mapped semantic icon (Task 5 registry) and severity color token;
  - assert `<VmsToaster />` mounts sonner's `<Toaster />` with our position (bottom-right), theme bound to `data-theme`, and elevation `z-toast` (Task 4);
  - assert error toasts render `aria-live="assertive"`, others `polite` (sonner supports `important`/richColors config — assert our config).
  Run → fails.
- [ ] Implement `toast.ts` wrapper around `sonner`'s `toast` + a `VmsToaster` component configuring position, theme, richColors off (we supply our own tokens/icons), close button, and `z-toast`. Map severity → `{ icon: <Icon name=... />, className: color token }`.
- [ ] Mount `<VmsToaster />` at the app root (where `ToastProvider` was mounted) and remove the old provider mount.
- [ ] Migrate every call-site from the old imperative API to `toast.*`. Delete `Toast.tsx` + `ToastProvider` + `ToastItem` type and the old store slice only after all consumers migrate (confirm via grep). Remove `@radix-ui/react-toast` from deps if nothing else uses it.
- [ ] Run tests → pass; run full suite to catch migrated call-sites.

**Verify:** `pnpm test:run` full suite green; `grep -rn "ToastProvider\|ToastItem"` returns nothing; `pnpm typecheck` clean.

**Commit:** `refactor: migrate toasts to sonner with VMS token/icon wrapper (§V.1)`

**Acceptance (spec §V.1 checklist):** sonner-backed; `toast.success/error/warning/info` wrapper; severity → token color + semantic icon; bottom-right, theme-bound, `z-toast`; a11y `aria-live`; old Radix toast fully removed; all call-sites migrated.

---

## Phase wrap-up (after Task 15)

- [ ] Run the full frontend quality gate one final time: `cd frontend; pnpm lint; pnpm typecheck; pnpm test:run`.
- [ ] Confirm coverage: `src/shared/` ≥ 80%, `src/features/` ≥ 70%.
- [ ] Run the visual-restraint gate over all of `src/` (Task 14) → exits 0.
- [ ] Verify the three-tier color model end-to-end: brass only on logo + active nav indicator; all buttons/toggles/focus rings charcoal; red only on severity.
- [ ] Update this plan's `**Status:**` line to `COMPLETE` with the date and final test count.
- [ ] Write/append implementation notes at `docs/superpowers/notes/2026-07-07-vms-phase4l-implementation-notes.md` — record: any icons added beyond the 36-set, any documented lucide exceptions, glass values used, nav gaps found/fixed, ActionBar adoption follow-ups, and any deferred-token decisions.
- [ ] Update CLAUDE.md §3: mark Phase 4L COMPLETE with milestone summary; set the next active phase.
- [ ] Confirm deferred 4M items (§D/E/I/F/J/Q/P/R/V.2) are still listed as deferred and packages installed in Task 1 are noted as "4M consumers".

---

## Dependency order summary

```
Task 1 (packages)
  └─ Task 2 (§G tokens) ── foundation for everything
       ├─ Task 3 (§H motion)
       ├─ Task 4 (§C elevation)
       └─ Task 5 (§B icons)
            └─ Task 6 (§A primitives)          [needs Task 4 elevation]
                 └─ Task 7 (§A Button/Card)    [needs Task 6]
                      ├─ Task 8 (§K badge)     [needs Task 5 icons]
                      ├─ Task 9 (§L skeletons)
                      ├─ Task 10 (§M glass)    [needs Task 4]
                      ├─ Task 11 (§O micro)    [needs Task 3 motion]
                      ├─ Task 12 (§N nav)      [needs Task 3, Task 2]
                      ├─ Task 13 (§S ActionBar)[needs Task 6, 7, 4, 10]
                      ├─ Task 14 (§T restraint gate)
                      └─ Task 15 (§V.1 sonner) [needs Task 5 icons, Task 4]
```

Each task is a single focused engineer session (30–90 min). Do not start a task before the previous dependency landed and its quality gate passed. Do not begin any Phase 4M item — those are explicitly out of scope.
