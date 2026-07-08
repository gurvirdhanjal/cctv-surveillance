# Phase 4O — UI States & Premium Details Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: NOT STARTED**

**Goal:** Implement the UI-state doctrine (spec Part III) — every route handles loading,
empty, error, offline/degraded, permission-denied — and the premium-feel details (Part IV):
shared time/number formatters, live-updating timestamps, chart token ramp, command-palette
completeness, login brand moment, themed scrollbars, toast cap.

**Architecture:** Pure frontend. New shared utils (`useNow`, `formatCount`,
`formatDuration`, `formatTs`), new UI states in live/analytics features, `--chart-1..6`
tokens consumed by `useChartTheme`, CommandPalette action group, login-page styling.

**Tech Stack:** React 18 + TypeScript + Vite, Tailwind tokens, Framer Motion, ECharts
(`EChartsWrapper` + `useChartTheme`), cmdk, Sonner, Vitest + Testing Library.

**Spec refs:** `2026-07-08-vms-frontend-premium-polish.md` Parts III–IV, §10 edge cases,
§13.3 chart ramp; `docs/frontend/2026-06-24-vms-design-system.md`;
`2026-07-06-vms-enterprise-interaction-guidelines.md` (do not contradict operator workflow).

**Depends on:** Phase 4N complete (tokens, unified AlertCard, AppSidebar shells).

**Frontend gate (every task):** `cd frontend && pnpm lint && pnpm typecheck && pnpm test:run`

---

## Task 1 — Shared formatters + `useNow`

- [ ] Tests first: `src/shared/utils/format.test.ts` —
      `formatCount(999)='999'`, `formatCount(1234)='1.2k'`, `formatCount(2_500_000)='2.5M'`;
      `formatDuration(45)='45s'`, `formatDuration(90)='1m 30s'`, `formatDuration(3700)='1h 1m'`;
      `formatTs(utcNaiveIso)` returns localized string and `formatTsRelative(iso, now)`
      returns 'just now'/'3m ago'/'2h ago'/'5d ago'. Run → fails.
- [ ] Implement `src/shared/utils/format.ts`. `formatTs*` are the ONLY places calling
      `new Date(iso)` on API timestamps (UTC-naive → treat as UTC: append 'Z' if absent).
- [ ] Tests first: `src/shared/hooks/useNow.test.ts` — returns Date, re-renders on the
      given interval (fake timers), shared single interval across mounts. Run → fails.
- [ ] Implement `useNow(intervalMs = 30_000)` with a module-level subscriber set (one
      `setInterval` total, not per component).
- [ ] Verify: gate green.

## Task 2 — Migrate ad-hoc time/count code to the shared utils

- [ ] Replace local `timeSince` in `AlertCard` (unified) and any other copies
      (`grep -rn "timeSince\|60_000" src/features/`) with `formatTsRelative` + `useNow(30_000)`
      so "3m ago" updates live; absolute time on `title` hover via `formatTs`.
- [ ] Replace ad-hoc count/duration math in TopBar, SystemStatusStrip, pager labels,
      KPI cards with `formatCount`/`formatDuration`.
- [ ] Add rule note to design-system doc: components never call `new Date(iso)` directly.
- [ ] Update affected tests (fake timers where relative time is asserted).
- [ ] Verify: `grep -rn "new Date(" src/features/ | grep -v test` shows only
      non-timestamp uses (or none); gate green.

## Task 3 — FocusedCamera stream-error + empty states

- [ ] Tests first: FocusedCamera — (a) no camera selected → "Select a camera" designed
      empty state; (b) MJPEG `<img>` onError → "Stream unavailable" card with Retry
      button (re-mounts stream with cache-busting param) and automatic snapshot-fallback
      poll (reuse `useCameraSnapshot`) labeled "Live paused — showing snapshots";
      (c) retry restores stream on success. Run → fails.
- [ ] Implement per spec §6 matrix row. Tokens only; `role="status"` on the error card.
- [ ] Verify: gate green.

## Task 4 — LivePage empty + stale states

- [ ] Tests first: (a) `cameras=[]` after snapshot load → EmptyState "No cameras" with
      role-gated admin CTA (may already exist via Task 4N-11 — extend to full-page
      layout); (b) when socket disconnected >10s, alert sidebar header shows an amber
      "Stale — reconnecting" badge that clears on reconnect. Run → fails.
- [ ] Implement: stale badge driven by existing socket status in `liveStore` +
      `useNow(1_000)` against `lastEventAt`.
- [ ] Verify: gate green.

## Task 5 — Analytics error/staleness rendering

- [ ] Tests first: AnalyticsDashboardPage — (a) KPI fetch failure renders an inline
      error card (message + Retry) in the KPI row instead of silent skeletons;
      (b) chart fetch failure renders error card in the chart frame; (c) "Updated Xs ago"
      caption near the KPI row turns `text-[var(--warning)]` when >60s. Run → fails.
- [ ] Implement using the captured-but-unused `kpiError` state; Retry re-triggers the
      query. Extract a small `InlineError` design-system component (message + Retry +
      `role="alert"`) — reused by Task 3's stream card if shapes align.
- [ ] Verify: gate green.

## Task 6 — Button `loading` prop + mutation pending states

- [ ] Tests first: design-system Button with `loading` — shows inline 16px spinner
      (existing Spinner), disables, keeps width (no layout shift; assert fixed min-width
      or spinner replacing label in place), `aria-busy`. Run → fails.
- [ ] Implement `loading?: boolean` on Button.
- [ ] Adopt on mutation triggers: alert Acknowledge/Resolve, ClipExportDialog submit,
      zone/camera/maintenance/routing save buttons (sweep `useMutation`-style handlers:
      `grep -rn "isPending\|isLoading" src/features/` and wire where a Button triggers it).
- [ ] Error toasts: audit `vmsToast.error` calls — every message states what failed +
      next step; no raw `error.message` pass-through (wrap with context).
- [ ] Verify: gate green.

## Task 7 — Page transitions + command palette completeness

- [ ] Forensic (now inside the Analytics shell, 4N Task 9): confirm the pathname-keyed
      fade covers it; add test. Assert /live has NO transition wrapper (test: LivePage
      tree contains no AnimatePresence around Outlet — it has no Outlet; assert none added).
- [ ] Tests first: CommandPalette — new "Actions" group with: Toggle theme,
      Acknowledge all visible alerts (live only, role-gated), Export audit log (admin,
      deep-link), Open shortcut legend; recents still persist; groups filter correctly.
      Run → fails.
- [ ] Implement actions group (deep-links + store calls); keep cmdk perf (no fetch on
      open beyond existing).
- [ ] TopBar (live) + admin/analytics header: `⌘K` hint chip — `bg-surface-chip
      text-text-muted text-label-xs font-mono rounded px-1.5` with `Ctrl+K` shown on
      non-mac (`navigator.platform` check util).
- [ ] Verify: gate green.

## Task 8 — Login brand moment

- [ ] LoginPage: brass primary CTA (`bg-[var(--brand-accent)]` — permitted brand moment),
      logo glow (exists), product name in `font-display display-md`, subtle background
      texture (CSS-only radial grid / scanlines ≤3% opacity via `--brand-accent-rgb`),
      card on `--surface-card` with `--shadow-3`.
- [ ] Respect reduced motion/transparency (static background under either preference).
- [ ] Update LoginPage tests + a11y test (contrast unaffected — texture behind card only).
- [ ] Verify: restraint gate still green (brass usage is within the login allowlist —
      extend the gate's allowlist config explicitly for LoginPage CTA if it trips).

## Task 9 — Chart theming (`--chart-1..6`)

- [ ] Add `--chart-1..6` to both theme blocks per spec §13.3; map in tailwind config only
      if classes needed (charts read via JS).
- [ ] Tests first: `useChartTheme.test.ts` — series palette reads the six CSS vars from
      the active theme scope; gridlines = `--border-default`; axis labels = `--text-muted`;
      tooltip bg = `--surface-card`. Run → fails.
- [ ] Update `useChartTheme` to resolve vars via `getComputedStyle` on the chart's
      container (theme-scoped, not documentElement — a light-admin chart and a future
      dark chart must resolve differently).
- [ ] Sweep the 3 ECharts charts: no inline hex colors; severity-colored series only
      where the series IS severity data (alert-volume by severity keeps `--severity-*`).
- [ ] Verify: charts render correctly in light admin/analytics; gate green.

## Task 10 — Scrollbars, titles, toast cap

- [ ] Themed thin scrollbars in `index.css`: `scrollbar-width: thin` +
      `scrollbar-color: var(--border-strong) transparent`; WebKit equivalents
      (8px, thumb `--border-strong`, hover `--text-muted`, track transparent). Applies
      globally; verify dark /live and light /admin.
- [ ] Helmet audit: every route sets a title (`grep -rLn "Helmet" src/features/**/**Page.tsx`
      style sweep); add missing (error pages included: "Not found — VMS").
- [ ] Sonner `visibleToasts={3}` on VmsToaster + test.
- [ ] Verify: gate green.

## Task 11 — Phase close-out

- [ ] Edge-case spot checks from spec §10 relevant to this phase: zero-data states on
      all lists/charts (tests exist per tasks above); 401 mid-session single redirect
      (verify existing client interceptor, add test if uncovered); 200-char name
      truncation on CameraRow/AlertCard (add fixture test).
- [ ] Full gate + coverage floors; restraint gate green.
- [ ] Update CLAUDE.md §3; write
      `docs/superpowers/notes/2026-07-08-vms-phase4o-implementation-notes.md`;
      plan Status → COMPLETE.
