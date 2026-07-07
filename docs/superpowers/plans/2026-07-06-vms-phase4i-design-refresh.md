# Phase 4I — Design System Refresh: Color Separation, Component Polish, and UX Foundations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE**

**Goal:** Correct the design system's three-tier color model (brand identity / action / alarm — each distinct). Polish components with consistent empty states, page headers, motion, skeleton loading, and expanded 12-state camera status vocabulary. Produce a SaaS-grade light mode that matches the quality of tools like Linear, Vercel, or Retool while remaining appropriate for a control-room surveillance product.

**Architecture:** All color changes propagate via CSS custom properties and Tailwind tokens — `index.css` and `tailwind.config.ts` are the root; changing them propagates to every component. Component tasks are additive (new shared components) or surgical (active state classes on existing layouts). Docs (Task 0) are complete.

**Tech Stack:** CSS custom properties, Tailwind CSS 3.4, React 18, TypeScript 5.4, Lucide icons

**Spec refs:**
- `docs/frontend/2026-06-24-vms-design-system.md` (§2.0 three-tier color model, §6.1 CSS vars, §7, §9 motion, §14.6 status)
- `docs/superpowers/specs/2026-07-06-vms-enterprise-interaction-guidelines.md` §§2–4

---

## Color Philosophy (binding — read before touching any token)

**Tier 1 — Brand Identity (crimson, sparse):** `brand-500 = #c0392b` — logo, 3px nav active left-bar. ≤ 5 elements per page. Never on buttons, focus rings, selections.

**Tier 2 — Action / Interactive (dark charcoal):** `action-700 = #1e293b` — all primary buttons, toggles, focus rings. Neutral. Does not compete with alarms.

**Tier 3 — Alarm / Severity (bright red, exclusive):** `severity-critical = #dc2626` — only on alarm badges, alarm card borders, device fault indicators. Exclusive use preserves its instant readability.

---

## Token Reference

### Brand scale (accent only)
| Token | Hex | Use |
|---|---|---|
| `brand-50` | `#fff1f0` | Hover wells (rare) |
| `brand-100` | `#ffe4e1` | Light bg (avoid) |
| `brand-500` | `#c0392b` | Logo, nav active left-bar — nothing else |
| `brand-700` | `#9b2226` | Hover on brand-accented elements |
| `brand-950` | `#3b0a0a` | Dark context accent |

### Action scale (primary interactive)
| Token | Hex | Use |
|---|---|---|
| `action-600` | `#334155` | Secondary hover bg |
| `action-700` | `#1e293b` | Primary button fill, toggle fill |
| `action-800` | `#0f172a` | Button hover |
| `action-900` | `#020617` | Button pressed |

---

## Implementation Audit Findings (2026-07-06)

From code review against Phase 4A–4H implementation:

| Item | Current state | Required state |
|---|---|---|
| `--focus-ring` in index.css | `#2b6cb0` (blue) | `#1e293b` (charcoal) |
| `--interactive-hover` | `#1a4480` (blue) | `#0f172a` (charcoal) |
| `--interactive-active` | `#102a4c` (blue) | `#020617` (charcoal) |
| `--selected-row` | `#eef6ff` (blue-50) | `#f1f5f9` (neutral) |
| `--brand-accent` | not present | `#c0392b` (new var) |
| `--interactive-primary` | not present | `#1e293b` (new var) |
| `--duration-*` vars | not present | all 5 duration vars |
| brand scale in tailwind | `#2b6cb0` (blue) | `#c0392b` (crimson) |
| `action` scale in tailwind | not present | add `action-600/700/800/900` |
| Button.tsx primary | `bg-brand-500` (#2b6cb0 blue) | `bg-action-700` (#1e293b) |
| Admin sidebar active | `bg-brand-500/15 text-brand-300` (blue) | `border-l-[3px] border-[--brand-accent] bg-white/5` |
| Analytics sidebar active | `bg-brand-50 text-brand-700` (blue) | `border-l-[3px] border-[--brand-accent] bg-surface-sunken` |
| LoginPage brand accent | none | `border-t-[3px] border-[--brand-accent]` on card |
| `src/shared/components/` | **does not exist** | create under `src/shared/design-system/components/` |
| PageHeader component | missing | `src/shared/design-system/components/PageHeader.tsx` |
| EmptyState (shared) | only in `src/features/admin/components/` | promote to `src/shared/design-system/components/` |
| Skeleton component | missing | `src/shared/design-system/components/Skeleton.tsx` |
| CameraStatusBadge | 4-state inline; not a component | `src/shared/design-system/components/CameraStatusBadge.tsx` |
| Loading text patterns | 10 files with `Loading…` text | replace with per-component skeletons |

---

## ✅ Task 0 — Design system rulebook (COMPLETE)

All docs have been updated:
- `docs/frontend/2026-06-24-vms-design-system.md` — three-tier model, action scale, 12-state status, motion table, improved empty states
- `docs/superpowers/specs/2026-07-06-vms-enterprise-interaction-guidelines.md` — created
- `CLAUDE.md §3` — updated

---

## Task 1 — CSS tokens + motion vars (index.css)

This is the foundation. Every subsequent task depends on these vars existing.

- [ ] Edit `frontend/src/index.css`:
  - Add to `:root` (theme-invariant — before the `[data-theme]` blocks):
    ```css
    :root {
      --duration-fast:     100ms;
      --duration-quick:    120ms;
      --duration-base:     180ms;
      --duration-slow:     200ms;
      --duration-flash:    600ms;
      --easing-standard:   cubic-bezier(0.4, 0, 0.2, 1);
      --easing-emphasized: cubic-bezier(0.2, 0, 0, 1);
    }
    ```
  - In `[data-theme="light"]` block — change/add these vars:
    ```css
    --interactive-primary: #1e293b;  /* action-700 — new */
    --brand-accent:        #c0392b;  /* crimson — new, sparse */
    --focus-ring:          #1e293b;  /* was #2b6cb0 blue */
    --interactive-hover:   #0f172a;  /* was #1a4480 blue */
    --interactive-active:  #020617;  /* was #102a4c blue */
    --selected-row:        #f1f5f9;  /* was #eef6ff blue-50 */
    ```
  - In `[data-theme="dark"]` block: update **only** these two vars (dark sidebar + Guard view):
    ```css
    --focus-ring:    #94a3b8;  /* slate-400 — charcoal is invisible on dark */
    --selected-row:  #1e293b;  /* neutral raised, not blue */
    ```
  - Do NOT touch any other dark-theme tokens (severity, surface, text vars — those are final)
  - Do NOT touch severity vars
- [ ] Run `pnpm lint` → clean
- [ ] Verify: `grep "#2b6cb0\|#1a4480\|#102a4c\|#eef6ff" src/index.css` returns 0 hits in the light block

---

## Task 2 — Tailwind config: brand accent + action scales

- [ ] Edit `frontend/tailwind.config.ts`:
  - Replace `brand` scale:
    ```ts
    brand: {
      50:  '#fff1f0',
      100: '#ffe4e1',
      500: '#c0392b',  // accent only
      700: '#9b2226',
      950: '#3b0a0a',
    },
    ```
  - Add `action` scale (new):
    ```ts
    action: {
      600: '#334155',
      700: '#1e293b',
      800: '#0f172a',
      900: '#020617',
    },
    ```
  - Add `transitionDuration` to extend:
    ```ts
    transitionDuration: {
      fast:  'var(--duration-fast)',
      quick: 'var(--duration-quick)',
      base:  'var(--duration-base)',
      slow:  'var(--duration-slow)',
    },
    ```
  - Remove old brand-300 (`#7eb0ff`) — that was a blue dark-theme focus color, no longer used
- [ ] Run `pnpm typecheck` → clean
- [ ] Run `pnpm test:run` → all tests pass (Tailwind purge won't break existing classes — action-* are new additions)

---

## Task 3 — Button.tsx: primary → action-700

**File:** `frontend/src/shared/design-system/components/Button.tsx`

- [ ] Read current primary variant classes
- [ ] Replace `bg-brand-500` on primary variant with `bg-action-700 hover:bg-action-800 active:bg-action-900`
- [ ] Keep all other variants unchanged (secondary, ghost, destructive)
- [ ] Run `pnpm test:run` → `Button.test.tsx` passes
- [ ] Verify: grep `bg-brand-500` in Button.tsx returns 0 hits

---

## Task 4 — Login page brand accent

**File:** `frontend/src/features/auth/LoginPage.tsx`

- [ ] Add `border-t-[3px] border-[var(--brand-accent)]` to the login card container
- [ ] Add shield/lock icon (24px, `text-[var(--brand-accent)]`) above the VMS wordmark
- [ ] Ensure page background is `bg-surface-sunken` (neutral, not warm-tinted)
- [ ] Run `pnpm test:run` → tests pass

---

## Task 5 — Admin sidebar: crimson 3px left-bar

**File:** `frontend/src/features/admin/AdminLayout.tsx`

Current active class: `bg-brand-500/15 text-brand-300` → shows blue. Must become crimson left-bar with minimal fill.

- [ ] Edit the nav item `className` for active state:
  - Active: `border-l-[3px] border-[var(--brand-accent)] bg-white/5 text-white pl-[calc(theme(spacing.3)_-_3px)]`
    _(subtract 3px from left padding to compensate for the border so items don't shift)_
  - Inactive hover: `hover:bg-white/5 hover:text-white/90 border-l-[3px] border-transparent`
  - Add `transition-colors duration-fast` to each item
- [ ] Nav section labels: ensure `text-[11px] font-semibold uppercase tracking-[0.08em] text-white/40 px-3 mt-4 mb-1`
- [ ] Run `pnpm test:run` → tests pass

---

## Task 6 — Analytics sidebar: crimson 3px left-bar

**File:** `frontend/src/features/analytics/AnalyticsLayout.tsx`

Current active: `bg-brand-50 text-brand-700` → shows blue. Must become crimson left-bar.

- [ ] Edit active nav item class:
  - Active: `border-l-[3px] border-[var(--brand-accent)] bg-surface-sunken font-medium text-text-primary pl-[calc(theme(spacing.3)_-_3px)]`
  - Inactive: `border-l-[3px] border-transparent text-text-secondary hover:bg-surface-sunken transition-colors duration-fast`
- [ ] Run `pnpm test:run` → tests pass

---

## Task 7 — PageHeader shared component

**File path:** `frontend/src/shared/design-system/components/PageHeader.tsx`
_(Note: NOT `src/shared/components/` — that directory does not exist)_

- [ ] Write test: `frontend/src/shared/design-system/components/PageHeader.test.tsx`
  - renders `h1` with `title`
  - renders optional `subtitle`
  - renders optional `actions` slot
  - `h1` has correct semantic level
- [ ] Run test → fails
- [ ] Create `PageHeader.tsx`:
  ```tsx
  interface PageHeaderProps {
    title: string;
    subtitle?: string;
    actions?: React.ReactNode;
    className?: string;
  }
  export function PageHeader({ title, subtitle, actions, className }: PageHeaderProps) {
    return (
      <div className={cn('flex items-start justify-between mb-6', className)}>
        <div>
          <h1 className="text-[22px] font-bold text-text-primary leading-tight">{title}</h1>
          {subtitle && (
            <p className="mt-1 text-[13px] text-text-muted">{subtitle}</p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    );
  }
  ```
- [ ] Run test → passes
- [ ] Adopt in admin pages that have ad-hoc `<h1>` or header divs:
  - `AdminDashboardPage.tsx`
  - `AdminPersonsPage.tsx`
  - `AdminCamerasPage.tsx`
  - `UsersPage.tsx` (if it has an h1)
  - `AuditLogViewerPage.tsx`
- [ ] Export from `src/shared/design-system/index.ts` (if such a barrel exists)
- [ ] Run `pnpm test:run` → all tests pass

---

## Task 8 — EmptyState: promote to shared design-system

A partial `EmptyState` exists in `src/features/admin/components/`. This task promotes it to the shared design-system level and standardizes its API.

- [ ] Read `src/features/admin/components/EmptyState.tsx` (understand current API)
- [ ] Write test: `frontend/src/shared/design-system/components/EmptyState.test.tsx`
  - renders LucideIcon + heading + body
  - renders optional CTA button when `cta` prop provided
  - no CTA rendered when `cta` is undefined
- [ ] Run test → fails (shared component doesn't exist)
- [ ] Create `frontend/src/shared/design-system/components/EmptyState.tsx`:
  ```tsx
  interface EmptyStateProps {
    icon: LucideIcon;
    heading: string;
    body: string;
    cta?: { label: string; onClick: () => void };
    className?: string;
  }
  export function EmptyState({ icon: Icon, heading, body, cta, className }: EmptyStateProps) {
    return (
      <div className={cn('flex flex-col items-center justify-center py-16 text-center', className)}>
        <Icon className="h-10 w-10 text-text-muted opacity-40" aria-hidden="true" />
        <p className="mt-4 text-[15px] font-semibold text-text-primary">{heading}</p>
        <p className="mt-1 text-[13px] text-text-muted max-w-xs">{body}</p>
        {cta && (
          <Button variant="primary" onClick={cta.onClick} className="mt-5">
            {cta.label}
          </Button>
        )}
      </div>
    );
  }
  ```
- [ ] Run test → passes
- [ ] Update all pages that import from `src/features/admin/components/EmptyState` to use the shared version
- [ ] Delete or deprecate `src/features/admin/components/EmptyState.tsx` (replace with re-export pointing to shared if it breaks other imports)
- [ ] Run `pnpm test:run` → all tests pass

---

## Task 9 — CameraStatusBadge: 12-state component

**This task was missing from the plan.** The design system defines a 12-state camera status model; no such component exists.

**File:** `frontend/src/shared/design-system/components/CameraStatusBadge.tsx`

- [ ] Write test: `CameraStatusBadge.test.tsx`
  - renders correct label for each of the 12 states
  - applies `animate-status-pulse` class only for `recording`, `streaming`, `reconnecting`, `recovering`
  - renders the correct Lucide icon for each state
  - accessible: `role="status"` or `aria-label`
- [ ] Run test → fails
- [ ] Create `CameraStatusBadge.tsx` implementing all 12 states from design-system.md §14.6:
  ```tsx
  type CameraStatus = 'recording' | 'streaming' | 'connected' | 'analytics' |
    'maintenance' | 'standby' | 'reconnecting' | 'unauthorized' |
    'unreachable' | 'offline' | 'recovering' | 'disabled';

  const STATUS_CONFIG: Record<CameraStatus, {
    label: string;
    colorClass: string;
    Icon: LucideIcon;
    pulse: boolean;
  }> = {
    recording:    { label: 'Recording',    colorClass: 'text-green-600',  Icon: Radio,       pulse: true  },
    streaming:    { label: 'Streaming',    colorClass: 'text-green-500',  Icon: Play,        pulse: true  },
    connected:    { label: 'Connected',    colorClass: 'text-green-400',  Icon: CheckCircle2,pulse: false },
    analytics:    { label: 'Analytics',    colorClass: 'text-blue-500',   Icon: Cpu,         pulse: false },
    maintenance:  { label: 'Maintenance',  colorClass: 'text-blue-400',   Icon: Calendar,    pulse: false },
    standby:      { label: 'Standby',      colorClass: 'text-gray-400',   Icon: Moon,        pulse: false },
    reconnecting: { label: 'Reconnecting', colorClass: 'text-amber-500',  Icon: RefreshCw,   pulse: true  },
    unauthorized: { label: 'Unauthorized', colorClass: 'text-amber-600',  Icon: ShieldX,     pulse: false },
    unreachable:  { label: 'Unreachable',  colorClass: 'text-gray-500',   Icon: WifiOff,     pulse: false },
    offline:      { label: 'Offline',      colorClass: 'text-gray-500',   Icon: XCircle,     pulse: false },
    recovering:   { label: 'Recovering',   colorClass: 'text-amber-400',  Icon: Activity,    pulse: true  },
    disabled:     { label: 'Disabled',     colorClass: 'text-gray-300',   Icon: MinusCircle, pulse: false },
  };
  ```
- [ ] Run test → passes
- [ ] Replace any inline status badge patterns in `AdminCamerasPage`, `CameraDetailPage`, `CameraTile` with `<CameraStatusBadge status={...} />`
- [ ] Run `pnpm test:run` → all tests pass

---

## Task 10 — Skeleton component + replace 10 loading patterns

**File:** `frontend/src/shared/design-system/components/Skeleton.tsx`

**Known loading text instances to replace (from audit):**
1. `AdminPersonsPage.tsx:65`
2. `AlertRoutingPage.tsx:115`
3. `AnomalyDetectorsPage.tsx:38`
4. `AuditLogViewerPage.tsx:93`
5. `HardwareTab.tsx:51`
6. `OverridesTab.tsx:92`
7. `CameraDetailPage.tsx:38`
8. `CameraDetailPage.tsx:153`
9. `MaintenanceCalendarPage.tsx:127`
10. `ZoneEditorPage.tsx:114`

- [ ] Write test: `Skeleton.test.tsx`
  - renders as `div` with `animate-pulse rounded bg-surface-raised`
  - `aria-hidden="true"`
- [ ] Run test → fails
- [ ] Create `Skeleton.tsx`:
  ```tsx
  interface SkeletonProps { className?: string; }
  export function Skeleton({ className }: SkeletonProps) {
    return (
      <div
        className={cn('animate-pulse rounded bg-surface-raised', className)}
        aria-hidden="true"
      />
    );
  }
  ```
- [ ] Also create composite skeletons in the same file or as separate files:
  - `PersonRowSkeleton` — avatar (h-10 w-10 rounded-full) + 2 lines
  - `CameraCardSkeleton` — 160×90 thumbnail block + label line
  - `KpiCardSkeleton` — big number block + label line
  - `AuditRowSkeleton` — 4 columns
- [ ] Run test → passes
- [ ] Replace each of the 10 loading text instances with appropriate skeleton:
  - List pages (persons, alerts, anomaly detectors, maintenance, zones): use `PersonRowSkeleton` × 8
  - Camera detail tabs (hardware, overrides): use card-level skeleton
  - Audit log: use `AuditRowSkeleton` × 10
  - Camera detail page: use `CameraCardSkeleton`
- [ ] Run `pnpm test:run` → all tests pass

---

## Task 11 — Card hover elevation (SaaS feel)

Enterprise SaaS tools (Linear, Vercel, Retool) give every card a subtle shadow elevation on hover. Currently VMS cards are flat on hover.

- [ ] Edit `AdminDashboardPage.tsx`:
  - Service health cards: add `hover:shadow-2 transition-shadow duration-fast cursor-default`
  - KPI cards: same
- [ ] Edit `AnalyticsDashboardPage.tsx`:
  - KPI cards: add `hover:shadow-2 transition-shadow duration-fast`
- [ ] Verify: cards do not already have hover shadow (check classes)
- [ ] Run `pnpm test:run` → tests pass

---

## Task 12 — Quality gate

- [ ] `pnpm lint` → 0 errors
- [ ] `pnpm typecheck` → 0 errors
- [ ] `pnpm test:run` → all tests pass
- [ ] `pnpm test:run --coverage` → `src/shared/` ≥ 80%, `src/features/` ≥ 70%
- [ ] Manual verification checklist (open in browser, light mode):
  - [ ] Primary button is dark charcoal (`#1e293b`), NOT blue or crimson
  - [ ] Focus ring is dark charcoal outline when tabbing — visible on white bg
  - [ ] Active nav items (admin sidebar): 3px crimson left-bar, no blue fill
  - [ ] Active nav items (analytics sidebar): 3px crimson left-bar, no blue bg
  - [ ] Login card: 3px crimson top border visible
  - [ ] EmptyState: every empty list shows icon + heading + body
  - [ ] Loading states: no plain "Loading…" text — skeletons show instead
  - [ ] Camera status: badges show operational labels (Recording/Streaming/not just Online)
  - [ ] Dark mode (toggle to dark): Guard view unchanged — no charcoal buttons (dark already was dark)
  - [ ] `grep "bg-brand-500" frontend/src` → 0 hits on primary buttons; only brand-accent uses allowed
- [ ] Update plan **Status** to COMPLETE
- [ ] Update CLAUDE.md §3

---

## Files touched

| File | Task | Change type |
|---|---|---|
| `frontend/src/index.css` | 1 | Add duration vars + update light-theme interactive tokens |
| `frontend/tailwind.config.ts` | 2 | Replace brand scale; add action + transitionDuration |
| `frontend/src/shared/design-system/components/Button.tsx` | 3 | Primary → `bg-action-700` |
| `frontend/src/features/auth/LoginPage.tsx` | 4 | Crimson top-border accent |
| `frontend/src/features/admin/AdminLayout.tsx` | 5 | Crimson left-bar active |
| `frontend/src/features/analytics/AnalyticsLayout.tsx` | 6 | Crimson left-bar active |
| `frontend/src/shared/design-system/components/PageHeader.tsx` | 7 | New |
| `frontend/src/shared/design-system/components/PageHeader.test.tsx` | 7 | New test |
| Various admin pages | 7 | Adopt PageHeader |
| `frontend/src/shared/design-system/components/EmptyState.tsx` | 8 | New (promoted from features/) |
| `frontend/src/shared/design-system/components/EmptyState.test.tsx` | 8 | New test |
| `src/features/admin/components/EmptyState.tsx` | 8 | Replace with import from shared |
| `frontend/src/shared/design-system/components/CameraStatusBadge.tsx` | 9 | New |
| `frontend/src/shared/design-system/components/CameraStatusBadge.test.tsx` | 9 | New test |
| Various camera pages | 9 | Use CameraStatusBadge |
| `frontend/src/shared/design-system/components/Skeleton.tsx` | 10 | New |
| `frontend/src/shared/design-system/components/Skeleton.test.tsx` | 10 | New test |
| 10 loading-text pages (see Task 10) | 10 | Replace Loading… with skeletons |
| `AdminDashboardPage.tsx`, `AnalyticsDashboardPage.tsx` | 11 | Card hover elevation |

---

## Hard constraints (never violate)

- `severity-critical: #dc2626` — never changed. Exclusive alarm signal.
- `[data-theme="dark"]` in `index.css` — not changed.
- Admin sidebar `data-theme="dark"` — stays. Intentional control-room choice.
- Alert card left-borders — severity colors only. `--brand-accent` never on alert components.
- `--status-maintenance: #2563eb` (blue) — stays. It is a semantic status color, not brand.
- New components created in `src/shared/design-system/components/` only — `src/shared/components/` does not exist and must not be created.
