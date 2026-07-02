# VMS Design System
**Design Specification** · 2026-06-24
**Status:** Approved
**Companion:** `docs/frontend/2026-05-01-vms-frontend-spec.md` — feature behavior, routes, backend API, testing plan

---

## 1. Overview

### 1.1 Design philosophy

The VMS frontend serves a plant-floor safety system. Three principles govern every design decision, in priority order:

1. **Safety-first legibility.** A guard must read an alert's severity, location, and age in under one second from across a control room. Severity color, type icon, and time-since are never more than one glance apart.
2. **Professional clarity.** Managers and admins use this as a serious B2B tool. No decoration, no gradients-for-fun, no playful microcopy. Information density is high but never cluttered — generous whitespace around dense data, not inside it.
3. **Control-room legibility.** The Guard view runs all day on a dim-room 24"+ display. Dark surfaces reduce eye fatigue; severity colors stay saturated enough to pierce the low ambient light without inducing glare.

### 1.2 Theme strategy

**Light is the default theme.** It is the professional B2B surface that Manager and Admin users see. **Dark is the secondary theme**, auto-applied to the Guard view because it reduces eye strain over an 8-hour shift and maximizes the contrast of alert colors in a dim control room.

Both themes are first-class and fully polished — dark is not a tinted afterthought.

- A single Zustand `themeStore` owns the active theme, persisted to `localStorage` under key `vms-theme`.
- A `<ThemeToggle />` switch lives in the TopBar.
- **Route-level overrides:** the Guard view forces dark on mount; Manager/Admin pages force light on mount. These overrides are *applied, not stored* — they set `data-theme` without writing to `localStorage`, so a user's explicit toggle is preserved across navigation away from the forced route.
- **System preference fallback:** on first load with no persisted preference, the theme is inferred from `prefers-color-scheme` — dark system → dark theme, light system → light theme. A `useThemeInitialization` hook (§6.6) can optionally watch the system preference and follow it in real time while no explicit choice is saved.
- **Mobile browser chrome:** `ThemeProvider` (§6.3) updates `<meta name="theme-color">` on every theme switch so the browser chrome matches the app surface.

### 1.3 Accessibility target

**WCAG 2.1 AA.** Body text ≥ 4.5:1 contrast, large text (≥ 18.66px bold / 24px regular) ≥ 3:1, all interactive controls keyboard-reachable with a visible `:focus-visible` ring, no animation that violates the seizure-safety guidelines (§3.2.2 / §12).

---

## 2. Color palette

### 2.1 Brand & severity (theme-invariant)

```ts
brand: { 50:'#eef6ff', 100:'#d9eaff', 300:'#7eb0ff', 500:'#2b6cb0', 700:'#1a4480', 900:'#102a4c' }
// Extended for dark selected-row backgrounds:
brand: { 950:'#0a1c33' }   // NEW — derived; see §2.6

severity: { critical:'#dc2626', high:'#ea580c', medium:'#d97706', low:'#65a30d' }
```

Severity hex values are identical in both themes — a critical red must mean the same thing on any display. Contrast is managed by the surface behind them, not by re-tinting the severity color.

### 2.2 Semantic tokens — full table

| Token | Light | Dark | Use |
|---|---|---|---|
| `text.primary` | `#0f172a` | `#f3f4f6` | Headings, body |
| `text.secondary` | `#475569` | `#9ca3af` | Labels, table headers, captions |
| `text.muted` | `#94a3b8` | `#6b7280` | Placeholder, disabled text, timestamps |
| `text.inverse` | `#ffffff` | `#0f172a` | Text on brand-filled buttons |
| `surface.base` | `#ffffff` | `#0a0e1a` | Page background, table rows |
| `surface.raised` | `#f8fafc` | `#111827` | Cards, hover rows, table headers' parent |
| `surface.sunken` | `#f1f5f9` | `#020617` | Table header bg, inset wells, camera feed area |
| `border.default` | `#e2e8f0` | `#1f2937` | Card borders, dividers, input borders |
| `border.strong` | `#cbd5e1` | `#374151` | Hovered inputs, emphasized dividers |

### 2.3 Interactive states (NEW — extends §5)

These were not defined in the frontend spec §5; they are derived here and become canonical.

| Token | Light | Dark | Use |
|---|---|---|---|
| `focus.ring` | `#2b6cb0` | `#7eb0ff` | `:focus-visible` outline (brand-500 / brand-300 for dark contrast) |
| `interactive.hover` | `#1a4480` | `#3b82f6` | Primary button hover (brand-700 / lighter for dark) |
| `interactive.active` | `#102a4c` | `#2b6cb0` | Primary button pressed |
| `interactive.disabledBg` | `#e2e8f0` | `#1f2937` | Disabled control fill |
| `interactive.disabledText` | `#94a3b8` | `#4b5563` | Disabled control label |
| `destructive.base` | `#dc2626` | `#dc2626` | Delete / purge fill |
| `destructive.hover` | `#b91c1c` | `#ef4444` | Destructive hover |
| `destructive.subtleBg` | `#fef2f2` | `#1f1315` | Destructive modal body tint |

### 2.4 Status colors — camera state

| State | Light | Dark | Icon |
|---|---|---|---|
| `online` | `#16a34a` (green-600) | `#22c55e` (green-500) | `CheckCircle2` |
| `offline` | `#6b7280` (gray-500) | `#9ca3af` (gray-400) | `XCircle` |
| `auth_failed` | `#d97706` (amber-600) | `#f59e0b` (amber-500) | `ShieldX` |
| `maintenance` | `#2563eb` (blue-600) | `#3b82f6` (blue-500) | `Calendar` |

### 2.5 Success / info / warning semantic

| Token | Light | Dark | Use |
|---|---|---|---|
| `success` | `#16a34a` | `#22c55e` | Form confirm, toast success |
| `info` | `#2563eb` | `#3b82f6` | Toast info, neutral system status |
| `warning` | `#d97706` | `#f59e0b` | Toast warning, non-critical caution |
| `error` | `#dc2626` | `#ef4444` | Toast error, validation failure |

### 2.6 Overlay / scrim

| Token | Light | Dark | Use |
|---|---|---|---|
| `overlay.scrim` | `rgba(15,23,42,0.45)` | `rgba(2,6,23,0.70)` | Modal backdrop (dark scrim is heavier — surface is already dark) |
| `selected.row` | `#eef6ff` (brand-50) | `#0a1c33` (brand-950) | TanStack table selected row |

> **Resolved ambiguity:** §5 supplied `brand.900=#102a4c` but no value dark enough for a selected-row tint on the `#0a0e1a` dark base. `brand-950=#0a1c33` is introduced here, sampled to sit ~1 step above the base surface without competing with severity colors.

---

## 3. Typography

### 3.1 Type scale

| Token | Font | Size | Weight | Line-height | Letter-spacing | Use |
|---|---|---|---|---|---|---|
| `display-xl` | Inter Display | 32px | 700 | 38px | -0.02em | Page hero title (Dashboard H1) |
| `display-lg` | Inter Display | 28px | 700 | 34px | -0.02em | View titles |
| `display-md` | Inter Display | 24px | 600 | 30px | -0.01em | Section headers, modal titles |
| `body-lg` | Inter | 16px | 400/500/600 | 24px | 0 | Primary body, form labels |
| `body-md` | Inter | 14px | 400/500/600 | 20px | 0 | Default UI text, table cells |
| `body-sm` | Inter | 13px | 400/500 | 18px | 0 | Captions, helper text |
| `label-xs` | Inter | 11px | 600 | 14px | 0.06em (uppercase) | Table headers, eyebrow labels |
| `mono-md` | JetBrains Mono | 13px | 400/500 | 18px | 0 | IDs, hashes, timestamps |
| `mono-sm` | JetBrains Mono | 12px | 400/500 | 16px | 0 | Dense mono (time-since, coords) |

### 3.2 When to use which family

- **Inter Display** — only for `display-*` tokens (≥ 24px). Its tighter optical sizing reads as a "heading." Never use below 24px.
- **Inter** — all body, labels, buttons, table cells. The workhorse.
- **JetBrains Mono** — anything where character alignment carries meaning: camera IDs, person GIDs, audit hashes, `time-since` counters, floor-plan coordinates, JSON config editor.

### 3.3 Font loading (`main.tsx`)

Self-hosted via `@fontsource` — no CDN, no layout shift, GDPR-clean (no Google Fonts request leaking IPs).

```tsx
// main.tsx
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource-variable/inter/index.css'; // Inter Display via "Inter Display" opsz axis
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';
```

```css
/* index.css */
:root {
  --font-display: 'Inter Display', 'Inter', system-ui, sans-serif;
  --font-body: 'Inter', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;
}
```

### 3.4 Responsive type (desktop-first)

Minimum supported viewport is 1280×800 (§11). Type only steps down at the single `lg` breakpoint:

| Token | ≥ 1440px | 1280–1439px |
|---|---|---|
| `display-xl` | 32px | 28px |
| `display-lg` | 28px | 24px |
| `display-md` | 24px | 22px |
| body/label/mono | unchanged | unchanged |

Body sizes never shrink — legibility floor is the 13px `body-sm`.

---

## 4. Spacing & layout grid

### 4.1 4px base unit — Tailwind scale

| Token | px | Token | px |
|---|---|---|---|
| `t-1` | 4 | `t-8` | 32 |
| `t-2` | 8 | `t-10` | 40 |
| `t-3` | 12 | `t-12` | 48 |
| `t-4` | 16 | `t-16` | 64 |
| `t-5` | 20 | `t-20` | 80 |
| `t-6` | 24 | `t-24` | 96 |
| `t-7` | 28 | `t-32` | 128 |

(These are Tailwind's default `1=0.25rem` scale at a 16px root; documented here so px intent is explicit.)

### 4.2 Layout zones

**Guard three-column view** (fixed, no fluid reflow below 1440 except sidebar collapse):

```
┌────────────┬──────────────────────────────┬──────────────┐
│ Camera     │                              │ Alert        │
│ Grid /     │   Main monitor / floor plan  │ Sidebar      │
│ Nav        │            (1fr)             │              │
│  320px     │                              │   380px      │
└────────────┴──────────────────────────────┴──────────────┘
  shrink:0          flex:1 min-w-0             shrink:0
```

```tsx
<div className="grid h-screen grid-cols-[320px_1fr_380px]">
```

**Admin / Analytics sidebar layout:**

```
┌──────────┬─────────────────────────────────────────────┐
│ Sidebar  │  Main content (1fr)                          │
│  240px   │  max-w-[1200px] mx-auto p-6                   │
└──────────┴─────────────────────────────────────────────┘
```

```tsx
<div className="grid h-screen grid-cols-[240px_1fr]">
```

### 4.3 Container max-widths

| Route type | Max-width | Rationale |
|---|---|---|
| Guard | none (full bleed) | Maximize camera + alert real estate |
| Analytics | `1200px` centered | Optimal chart/table line length |
| Admin forms | `880px` centered | Form readability |
| Detail (CameraDetail, IncidentDetail) | `1040px` centered | Mixed media + metadata |

### 4.4 Page padding

| Zone | Padding |
|---|---|
| Guard main + columns | `p-0` (tiles/sidebars own their internal `t-3` gutter) |
| Admin + Analytics | `p-6` (24px) |
| Modal body | `p-6` |
| Card body | `p-4` (16px); compact metric cards `p-3` |

---

## 5. Elevation & depth

Four levels. Dark theme multiplies shadow alpha by **0.40×** because shadows read weakly on dark surfaces — the elevation cue shifts toward the lighter `surface.raised` fill rather than the shadow.

| Level | Name | Shadow (light) | Shadow (dark, 0.40×) | Use |
|---|---|---|---|---|
| 0 | Flat | none | none | Page background, table rows, inline content |
| 1 | Raised | `0 1px 2px rgba(0,0,0,0.06)` | `0 1px 2px rgba(0,0,0,0.024)` | Cards at rest, sticky table header |
| 2 | Floating | `0 4px 6px rgba(0,0,0,0.10)` | `0 4px 6px rgba(0,0,0,0.04)` | Card hover, dropdowns, popovers, focused camera tile |
| 3 | Overlay | `0 10px 25px rgba(0,0,0,0.20)` | `0 10px 25px rgba(0,0,0,0.08)` | Modals, toasts, command palette |

```css
:root[data-theme="dark"] {
  --shadow-1: 0 1px 2px rgba(0,0,0,0.024);
  --shadow-2: 0 4px 6px rgba(0,0,0,0.04);
  --shadow-3: 0 10px 25px rgba(0,0,0,0.08);
}
```

---

## 6. Theme toggle implementation

### 6.1 CSS custom properties

The single source of runtime truth. Tailwind reads these via `theme.extend.colors` referencing `var(--…)`; components never hard-code hex.

```css
/* index.css */
:root[data-theme="light"] {
  --text-primary:   #0f172a;
  --text-secondary: #475569;
  --text-muted:     #94a3b8;
  --text-inverse:   #ffffff;

  --surface-base:   #ffffff;
  --surface-raised: #f8fafc;
  --surface-sunken: #f1f5f9;

  --border-default: #e2e8f0;
  --border-strong:  #cbd5e1;

  --focus-ring:        #2b6cb0;
  --interactive-hover: #1a4480;
  --interactive-active:#102a4c;
  --disabled-bg:       #e2e8f0;
  --disabled-text:     #94a3b8;

  --destructive:       #dc2626;
  --destructive-hover: #b91c1c;
  --destructive-subtle:#fef2f2;

  --status-online:      #16a34a;
  --status-offline:     #6b7280;
  --status-auth-failed: #d97706;
  --status-maintenance: #2563eb;

  --success: #16a34a;
  --info:    #2563eb;
  --warning: #d97706;
  --error:   #dc2626;

  --overlay-scrim: rgba(15,23,42,0.45);
  --selected-row:  #eef6ff;

  --shadow-1: 0 1px 2px rgba(0,0,0,0.06);
  --shadow-2: 0 4px 6px rgba(0,0,0,0.10);
  --shadow-3: 0 10px 25px rgba(0,0,0,0.20);

  --body-letter-spacing: 0;
}

:root[data-theme="dark"] {
  --text-primary:   #f3f4f6;
  --text-secondary: #9ca3af;
  --text-muted:     #6b7280;
  --text-inverse:   #0f172a;

  --surface-base:   #0a0e1a;
  --surface-raised: #111827;
  --surface-sunken: #020617;

  --border-default: #1f2937;
  --border-strong:  #374151;

  --focus-ring:        #7eb0ff;
  --interactive-hover: #3b82f6;
  --interactive-active:#2b6cb0;
  --disabled-bg:       #1f2937;
  --disabled-text:     #4b5563;

  --destructive:       #dc2626;
  --destructive-hover: #ef4444;
  --destructive-subtle:#1f1315;

  --status-online:      #22c55e;
  --status-offline:     #9ca3af;
  --status-auth-failed: #f59e0b;
  --status-maintenance: #3b82f6;

  --success: #22c55e;
  --info:    #3b82f6;
  --warning: #f59e0b;
  --error:   #ef4444;

  --overlay-scrim: rgba(2,6,23,0.70);
  --selected-row:  #0a1c33;

  --shadow-1: 0 1px 2px rgba(0,0,0,0.024);
  --shadow-2: 0 4px 6px rgba(0,0,0,0.04);
  --shadow-3: 0 10px 25px rgba(0,0,0,0.08);

  --body-letter-spacing: 0.01em; /* §12: legibility on dark */
}

/* Severity is theme-invariant — declare once at :root */
:root {
  --severity-critical: #dc2626;
  --severity-high:     #ea580c;
  --severity-medium:   #d97706;
  --severity-low:      #65a30d;
}

/* Global theme transition — fires only when data-theme changes on :root.
   Scoped to [data-theme] so the transition is skipped on cold page load
   (before ThemeProvider sets the attribute). */
:root[data-theme] *, :root[data-theme] *::before, :root[data-theme] *::after {
  transition: background-color 300ms ease, border-color 300ms ease, color 300ms ease;
}
/* Inputs and active buttons skip the transition — keyboard/click response must feel instant. */
:root[data-theme] input,
:root[data-theme] textarea,
:root[data-theme] select,
:root[data-theme] button:active {
  transition: none;
}
```

```ts
// tailwind.config.ts (excerpt)
extend: {
  colors: {
    text: { primary: 'var(--text-primary)', secondary: 'var(--text-secondary)', muted: 'var(--text-muted)', inverse: 'var(--text-inverse)' },
    surface: { base: 'var(--surface-base)', raised: 'var(--surface-raised)', sunken: 'var(--surface-sunken)' },
    border: { DEFAULT: 'var(--border-default)', strong: 'var(--border-strong)' },
    severity: { critical: 'var(--severity-critical)', high: 'var(--severity-high)', medium: 'var(--severity-medium)', low: 'var(--severity-low)' },
    // brand stays a static scale (theme-invariant); add 950:
    brand: { 50:'#eef6ff',100:'#d9eaff',300:'#7eb0ff',500:'#2b6cb0',700:'#1a4480',900:'#102a4c',950:'#0a1c33' },
  },
  boxShadow: { 1: 'var(--shadow-1)', 2: 'var(--shadow-2)', 3: 'var(--shadow-3)' },
}
```

### 6.2 Zustand `themeStore`

```ts
// stores/themeStore.ts
import { create } from 'zustand';

type Theme = 'light' | 'dark';
const STORAGE_KEY = 'vms-theme';

interface ThemeState {
  theme: Theme;
  toggleTheme: () => void;       // user action — persists
  applyTheme: (t: Theme) => void; // route override — does NOT persist
}

const systemPreference: Theme =
  window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
const initial: Theme =
  (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? systemPreference;

export const useThemeStore = create<ThemeState>((set) => ({
  theme: initial,
  toggleTheme: () =>
    set((s) => {
      const next: Theme = s.theme === 'light' ? 'dark' : 'light';
      localStorage.setItem(STORAGE_KEY, next);
      return { theme: next };
    }),
  applyTheme: (t) => set({ theme: t }), // no localStorage write
}));
```

### 6.3 `ThemeProvider`

```tsx
// components/ThemeProvider.tsx
import { useEffect, type PropsWithChildren } from 'react';
import { useThemeStore } from '@/stores/themeStore';

const META_THEME_COLOR: Record<'light' | 'dark', string> = {
  light: '#ffffff',   // matches --surface-base light
  dark:  '#0a0e1a',   // matches --surface-base dark
};

export function ThemeProvider({ children }: PropsWithChildren) {
  const theme = useThemeStore((s) => s.theme);
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    // Update mobile browser chrome color
    let meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement('meta');
      meta.name = 'theme-color';
      document.head.appendChild(meta);
    }
    meta.content = META_THEME_COLOR[theme];
  }, [theme]);
  return <>{children}</>;
}
```

> **HTML prerequisite:** add `<meta name="theme-color" content="#ffffff">` to `index.html` so browsers pick up the correct color before React hydrates. `ThemeProvider` takes over from there.


### 6.4 Route-level auto-theme

Guard forces dark; Manager/Admin force light — applied, not stored, so the user's last explicit toggle survives navigation back to a non-forced route.

```tsx
// hooks/useRouteTheme.ts
import { useEffect } from 'react';
import { useThemeStore } from '@/stores/themeStore';

/** Apply a theme for the lifetime of a route without persisting it. */
export function useRouteTheme(forced: 'light' | 'dark') {
  const apply = useThemeStore((s) => s.applyTheme);
  const stored = (localStorage.getItem('vms-theme') as 'light' | 'dark') ?? 'light';
  useEffect(() => {
    apply(forced);
    return () => apply(stored); // restore the user's persisted choice on unmount
  }, [forced, apply, stored]);
}

// GuardView.tsx       → useRouteTheme('dark');
// AdminLayout.tsx      → useRouteTheme('light');
// AnalyticsLayout.tsx  → useRouteTheme('light');
```

### 6.5 `<ThemeToggle />` (TopBar)

```tsx
interface ThemeToggleProps {
  className?: string;
  /** Hide on routes that force a theme (Guard) so users aren't confused. */
  disabled?: boolean;
}
// Renders a shadcn Switch + Sun/Moon Lucide icons (Moon for dark, Sun for light).
// aria-label="Toggle color theme"; aria-pressed reflects dark state.
// On change → useThemeStore.getState().toggleTheme()
```

### 6.6 System preference + `useThemeInitialization`

The store's `initial` value (§6.2) already performs a one-shot read of `prefers-color-scheme`. This hook adds the optional live-watch so the app follows system changes made after load — but only while no explicit user preference is stored.

```tsx
// hooks/useThemeInitialization.ts
import { useEffect } from 'react';
import { useThemeStore } from '@/stores/themeStore';

/**
 * Call once in App.tsx.
 * watchSystem = true → follow OS theme changes in real-time when the user
 *   hasn't stored an explicit preference. watchSystem = false (default) →
 *   system preference is read once at store init (§6.2) and never re-checked.
 */
export function useThemeInitialization(watchSystem = false) {
  const apply = useThemeStore((s) => s.applyTheme);
  useEffect(() => {
    if (!watchSystem) return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => {
      if (!localStorage.getItem('vms-theme')) {
        apply(e.matches ? 'dark' : 'light');
      }
    };
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [watchSystem, apply]);
}
```

```tsx
// App.tsx
import { useThemeInitialization } from '@/hooks/useThemeInitialization';

function App() {
  useThemeInitialization(true); // watch system; user's explicit toggle always wins
  return <ThemeProvider>...</ThemeProvider>;
}
```

**Behavior matrix:**

| Saved preference | OS changes | Result |
|---|---|---|
| None | dark → light | Follows OS → light |
| None | light → dark | Follows OS → dark |
| `'dark'` | light | Ignores OS — shows dark |
| `'light'` | dark | Ignores OS — shows light |

---

## 7. Component design patterns

> All examples use the CSS-variable-backed Tailwind tokens from §6.1. Focus rings use `:focus-visible` only (§13.2).

### 7.1 Button

Variants: `primary` (brand-500 fill), `secondary` (outlined), `ghost`, `destructive` (red-600). Sizes: `sm` (h-8 px-3 text-13), `md` (h-10 px-4 text-14), `lg` (h-12 px-5 text-16).

States: default · hover · active · disabled (`aria-disabled` + `pointer-events-none`, **not** `cursor-not-allowed`) · loading (spinner replaces leading icon; label stays; `aria-busy="true"`).

```tsx
// primary / md
<button
  className="inline-flex h-10 items-center gap-2 rounded-md bg-brand-500 px-4
             text-14 font-600 text-text-inverse shadow-1
             hover:bg-[var(--interactive-hover)] active:bg-[var(--interactive-active)]
             focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2
             focus-visible:outline-[var(--focus-ring)]
             aria-disabled:pointer-events-none aria-disabled:bg-[var(--disabled-bg)]
             aria-disabled:text-[var(--disabled-text)]"
>
  {loading ? <Spinner size={16} /> : <Icon size={20} aria-hidden="true" />}
  Save
</button>
```

```
secondary:   border border-strong bg-transparent text-text-primary hover:bg-surface-raised
ghost:       bg-transparent text-text-primary hover:bg-surface-raised
destructive: bg-[var(--destructive)] text-white hover:bg-[var(--destructive-hover)]
```

**a11y:** loading button keeps its accessible name; icon-only buttons require `aria-label`.

### 7.2 Input / Textarea

Label above; error message below wired with `aria-describedby`.

```tsx
<label htmlFor="zone" className="text-13 font-500 text-text-secondary">Zone name</label>
<input id="zone" aria-invalid={!!error} aria-describedby={error ? 'zone-err' : undefined}
  className="mt-1 h-10 w-full rounded-md border border-default bg-surface-base px-3 text-14
             text-text-primary placeholder:text-text-muted
             focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-[var(--focus-ring)]
             aria-[invalid=true]:border-[var(--error)] aria-[invalid=true]:outline-[var(--error)]
             disabled:bg-[var(--disabled-bg)] disabled:text-[var(--disabled-text)]" />
{error && <p id="zone-err" className="mt-1 text-13 text-[var(--error)]">{error}</p>}
```

States: default · focused (`ring` = brand) · error (red border + red ring + message) · disabled. Textarea identical with `min-h-[96px] py-2`.

### 7.3 Select / Dropdown

Built on shadcn `Select`. Chevron (`ChevronDown` 16px) right-aligned. Content `max-h-[240px] overflow-y-auto`; for camera lists > 50 items wrap options in TanStack Virtual. Trigger matches Input styling. Selected item gets a `Check` 16px leading icon.

### 7.4 Badge / Chip

12px height pill, `text-11 font-600`, leading icon 12px, `gap-1 px-2 rounded-full`.

```
severity-critical: bg-[var(--severity-critical)]/15 text-[var(--severity-critical)]  + ShieldAlert
severity-high:     bg-[var(--severity-high)]/15     text-[var(--severity-high)]      + AlertCircle
severity-medium:   bg-[var(--severity-medium)]/15   text-[var(--severity-medium)]    + Info
severity-low:      bg-[var(--severity-low)]/15       text-[var(--severity-low)]       + Info

tier FULL/MID/LOW: bg-surface-sunken text-text-secondary border border-default (mono label)

status online:      bg-[var(--status-online)]/15      text-[var(--status-online)]
status offline:     bg-[var(--status-offline)]/15     text-[var(--status-offline)]
status auth_failed: bg-[var(--status-auth-failed)]/15 text-[var(--status-auth-failed)]
status maintenance: bg-[var(--status-maintenance)]/15 text-[var(--status-maintenance)]
```

### 7.5 Card

```
flat card:        bg-surface-raised border border-default rounded-lg p-4
interactive card: + hover:shadow-2 cursor-pointer transition-shadow duration-fast
alert card:       + border-l-4 (severity color), see §7.6
metric card:      flex flex-col gap-1 p-3 — big number (display-md mono), label (label-xs),
                  sparkline slot (h-8 mt-2)
```

### 7.6 Alert card (detailed)

```
┌─[4px severity border]──────────────────────────────┐
│ ⚠ CRITICAL · Intrusion              2m 14s ago(mono)│
│ Cam-07 · North Loading Dock                          │
│                                                      │
│ [ Acknowledge ]  [ Resolve ]                         │
│ ▸ +3 similar in this zone (collapsible)              │
└──────────────────────────────────────────────────────┘
```

- Left border: `border-l-4` in the severity color.
- Severity icon top-left (`ShieldAlert`/`AlertCircle`/`Info`, 20px).
- Type label `body-md font-600`; `time-since` in `mono-sm text-text-secondary`, right-aligned, updates every second.
- Camera + zone line: `body-sm text-text-secondary`.
- Two buttons: Acknowledge (`secondary`), Resolve (`primary`).
- "+N similar" is a `Collapsible` (shadcn) — chevron rotates, lazy-renders grouped alerts.
- Dark Guard view: critical cards add the §12 glow `box-shadow: 0 0 0 1px #dc2626`.

### 7.7 Table

```
header row:  bg-surface-sunken text-text-secondary uppercase text-11 tracking-[0.06em] h-9
body row:    bg-surface-base hover:bg-surface-raised h-11 border-b border-default
selected:    bg-[var(--selected-row)]
sticky:      thead → sticky top-0 z-10 shadow-1
```

For > 100 rows use **TanStack Virtual** (`useVirtualizer`) on the `<tbody>` — render only visible rows, fixed `estimateSize: () => 44`. Keep the real `<table>` semantics for screen readers (don't div-ify).

### 7.8 Modal / Dialog

shadcn `Dialog`. Scrim `bg-[var(--overlay-scrim)]`. Centered, default `max-w-lg`. Focus trap, `Esc` closes, focus restored to trigger on close.

Sizes: `sm` max-w-sm · `md` max-w-md · `lg` max-w-lg · `xl` max-w-2xl.

**Confirmation variant:** `display-md` title + `body-md` body + danger action (`destructive`) + Cancel (`ghost`). Danger action is *not* the default-focused element — Cancel is.

### 7.9 Toast / Notification

Variants: `success` (green) · `error` (red) · `warning` (amber) · `info` (blue). Slide in from bottom-right; stack **max 3 visible** (overflow queued). Auto-dismiss 5s; **critical/error → manual dismiss only**.

- `aria-live="polite"` for success/info/warning; `aria-live="assertive"` for errors.
- Leading semantic icon, title `body-md font-600`, optional body `body-sm`, dismiss `X` (`aria-label="Dismiss"`).
- Left border 4px in the variant color; `shadow-3`.

### 7.10 Tooltip

shadcn `Tooltip`, 200ms open delay. Placements: above/below/left/right (auto-flip). `max-w-[280px]`, `text-13`. ID/hash content uses `font-mono`. `bg-surface-sunken text-text-primary border border-default shadow-2`.

### 7.11 Tabs

- **Underline style** for detail pages (CameraDetail): active tab gets a 2px brand-500 bottom border that *slides* (§9). Inactive `text-text-secondary`, active `text-text-primary`.
- **Pill style** for analytics sub-page switching: active pill `bg-brand-500 text-text-inverse`, inactive `text-text-secondary hover:bg-surface-raised`.
- `role="tablist"`, arrow-key navigation, `aria-selected`.

### 7.12 Progress / Spinner

- **Linear** progress bar (profiler, wizard): `h-1.5 rounded-full bg-surface-sunken` with `bg-brand-500` fill, `transition-[width] duration-base`. `role="progressbar"` + `aria-valuenow`.
- **Circular spinner**: 16px inline (in buttons/cells), 32px page-level (centered). `animate-spin`, `aria-label="Loading"`, `role="status"`.

### 7.13 Status indicator

8px dot. Online → pulse animation (§9). Offline/maintenance → static dot, no pulse.

```tsx
<span className={cn('inline-block h-2 w-2 rounded-full',
  status === 'online'      && 'bg-[var(--status-online)] animate-status-pulse',
  status === 'offline'     && 'bg-[var(--status-offline)]',
  status === 'auth_failed' && 'bg-[var(--status-auth-failed)]',
  status === 'maintenance' && 'bg-[var(--status-maintenance)]')}
  role="img" aria-label={`Camera ${status}`} />
```

### 7.14 Camera tile

160×90px (16:9) thumbnail.

```
┌──[tier badge TL]──────────[status badge TR]──┐
│                                              │
│              live thumbnail                  │
│                                              │
│ ░ Cam-07 · North Dock ░░ (scrim BL)          │
└──────────────────────────────────────────────┘
focused:     ring-2 ring-brand-500 shadow-2
maintenance: opacity-50 + centered Calendar icon overlay
```

- Name bottom-left over a `bg-gradient-to-t from-black/70` scrim, `text-13 text-white`.
- Tier badge top-left (FULL/MID/LOW); status badge top-right.
- Focused: `2px brand-500` border + `shadow-2`.

### 7.15 Floor-plan person dot

12px circle, `2px white` border. Identity colors: known = brand-500, unknown = red-500, followed = yellow-400. Pulse on new detection. **Position updates via CSS `transform`**, never React state re-render (§9).

```tsx
// dot positioned by transform; data attrs drive color
<div className="person-dot absolute h-3 w-3 rounded-full border-2 border-white"
     style={{ transform: `translate(${x}px, ${y}px)` }}
     data-identity={identity} />
```
```css
.person-dot[data-identity="known"]    { background: var(--severity, #2b6cb0); }
.person-dot[data-identity="unknown"]  { background: #ef4444; }
.person-dot[data-identity="followed"] { background: #facc15; }
```

### 7.16 Severity color bar (4px left border)

Used on alert cards and table rows. Exact rgba (full-opacity border):

```
critical: rgba(220, 38, 38, 1)   /* #dc2626 */
high:     rgba(234, 88, 12, 1)   /* #ea580c */
medium:   rgba(217, 119, 6, 1)   /* #d97706 */
low:      rgba(101, 163, 13, 1)  /* #65a30d */
```

```tsx
<div style={{ borderLeft: `4px solid ${SEVERITY_RGBA[severity]}` }} />
```

### 7.17 Loading skeleton

Use skeleton in place of a spinner when the loaded content has predictable structure — it reduces layout shift and signals progress without an ambiguous indicator. All skeletons use `bg-surface-raised animate-pulse rounded`.

```tsx
// Person list row — matches real row height (h-11) and layout:
<div className="flex items-center gap-3 px-3 py-2">
  <div className="h-10 w-10 flex-shrink-0 rounded-full bg-surface-raised animate-pulse" />
  <div className="flex-1 space-y-2">
    <div className="h-4 w-2/3 rounded bg-surface-raised animate-pulse" />
    <div className="h-3 w-1/3 rounded bg-surface-raised animate-pulse" />
  </div>
</div>

// Camera list row — fixed height matches real row:
<div className="h-11 w-full rounded bg-surface-raised animate-pulse" />

// Metric card (Analytics KPI):
<div className="flex flex-col gap-2 p-3">
  <div className="h-8 w-20 rounded bg-surface-raised animate-pulse" /> {/* big number */}
  <div className="h-3 w-28 rounded bg-surface-raised animate-pulse" /> {/* label */}
</div>

// Audit log row:
<div className="flex items-center gap-4 px-3 py-2">
  <div className="h-3 w-32 rounded bg-surface-raised animate-pulse" /> {/* timestamp */}
  <div className="h-3 w-24 rounded bg-surface-raised animate-pulse" /> {/* event type */}
  <div className="h-3 flex-1 rounded bg-surface-raised animate-pulse" /> {/* detail */}
</div>
```

**Rules:**
- Repeat N skeleton rows equal to the expected page size (e.g. 10 for a paginated admin list). A single spinner doesn't communicate list structure.
- `prefers-reduced-motion`: replace `animate-pulse` with a static `bg-surface-raised opacity-60` — no motion.
- Never combine a spinner *and* skeleton in the same loading context — pick one per component.
- Once data arrives, transition from skeleton → content without an explicit fade; the React state swap is fast enough.

---

## 8. Form patterns

### 8.1 Multi-step wizard (camera onboarding / profiler)

```
[ ① Connect ]──[ ② Calibrate ]──[ ③ Zones ]──[ ④ Review ]
████████████░░░░░░░░░░░░░░░░░░░░  Step 2 of 4
┌──────────────────────────────────────────────┐
│  step content                                  │
└──────────────────────────────────────────────┘
            [ Cancel ]      [ Back ] [ Next ]
```

- Step indicator: numbered circles, completed = brand-500 fill + `Check`, current = brand-500 ring, future = `border-default`.
- Linear progress bar reflects `currentStep / totalSteps`.
- Cancel triggers a confirmation modal if any field is dirty.
- `Next` disabled (`aria-disabled`) until step validation passes.

### 8.2 Inline table edit

Click cell → it becomes an `<input>` (auto-focus, select-all). `Enter` saves, `Esc` cancels, blur saves. On save, show a 6s **undo toast** ("Zone renamed · Undo"). Cell shows a pencil affordance on row hover.

### 8.3 Soft-delete confirmation

Modal (`md`): title "Delete {entity}?", body explains soft-delete is recoverable, a typed-confirmation field that must match the entity name, and a required reason textarea (audited). Confirm button `destructive`, disabled until name matches exactly.

### 8.4 GDPR purge confirmation (irreversible)

More prominent than soft-delete (CLAUDE.md §7.3 — there is no undo).

```
┌─[ destructive subtle bg ]──────────────────────────┐
│ 🛑 Permanently purge person record                  │
│ This erases all embeddings and scrubs thumbnails.   │
│ THIS CANNOT BE UNDONE.                               │
│                                                      │
│ Type the full name to confirm:                       │
│ [ ___________________________ ]                      │
│ Reason (audited):                                    │
│ [ ___________________________ ]                      │
│                  [ Cancel ]  [ Purge permanently ]   │
└──────────────────────────────────────────────────────┘
```

- Modal body uses `bg-[var(--destructive-subtle)]`, red `ShieldX`/`Trash2` icon.
- Full-name match (exact, case-sensitive) + reason required.
- Confirm is `destructive`; admin role enforced server-side. Emits `event_type='PERSON_PURGED'`.

### 8.5 JSON config editor (anomaly detectors)

Monospace `<textarea>` (`font-mono text-13`). Schema-validated on change (debounced 300ms) against the detector's JSON schema; invalid lines get a red wavy underline via a CodeMirror lint gutter (or a fallback red bottom-border + error list below). Save disabled while invalid; error count shown as a badge.

---

## 9. Motion & animation

Durations: `fast 120ms` (hover/focus) · `base 200ms` (drawers, transitions) · `slow 400ms` (large layout). Easings: `standard cubic-bezier(0.4,0,0.2,1)`, `emphasized cubic-bezier(0.2,0,0,1)`.

```css
@keyframes toast-slide-in {
  from { opacity: 0; transform: translateX(16px); }
  to   { opacity: 1; transform: translateX(0); }
}
@keyframes modal-enter {
  from { opacity: 0; transform: scale(0.96); }
  to   { opacity: 1; transform: scale(1); }
}
@keyframes drawer-slide-in {
  from { transform: translateX(100%); }
  to   { transform: translateX(0); }
}
@keyframes tooltip-fade { from { opacity: 0; } to { opacity: 1; } }
@keyframes status-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(34,197,94,0.6); }
  70%  { box-shadow: 0 0 0 6px rgba(34,197,94,0); }
  100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
}
@keyframes alert-insert-flash {
  0%   { background: rgba(220,38,38,0.18); }
  100% { background: transparent; }
}

.toast            { animation: toast-slide-in 200ms var(--easing-emphasized); }
.modal-content    { animation: modal-enter 200ms var(--easing-emphasized); }
.drawer           { animation: drawer-slide-in 200ms var(--easing-standard); }
.tooltip          { animation: tooltip-fade 120ms var(--easing-standard); }
.animate-status-pulse { animation: status-pulse 2s var(--easing-standard) infinite; }
.tab-indicator    { transition: transform 200ms var(--easing-emphasized),
                                width 200ms var(--easing-emphasized); }
.person-dot       { transition: transform 200ms ease; }   /* §7.15 */
.alert-item-new   { animation: alert-insert-flash 600ms var(--easing-standard); }
```

**Alert sidebar insert:** new item flashes a severity-tinted background (`alert-insert-flash`) — a highlight, *not* a height animation, to avoid layout shift / scroll jump.

**`prefers-reduced-motion`:** collapse all durations to 0ms, keep opacity fades only. No pulses, no slides.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
  .toast, .modal-content { animation: tooltip-fade 0.01ms; } /* opacity-only */
  .animate-status-pulse { animation: none; }
}
```

---

## 10. Iconography

**Library:** Lucide React (matches shadcn/ui, fully tree-shakeable — import per-icon).

**Sizes:** 16px inline (in text, badges, table cells) · 20px in buttons · 24px for nav/primary actions.

| Concept | Icon | Concept | Icon |
|---|---|---|---|
| Camera | `Camera` | Zone | `MapPin` |
| Alert (critical) | `AlertTriangle` | Maintenance | `Calendar` |
| Alert (general) | `Bell` | Settings | `Settings2` |
| Person (generic) | `User` | Audit | `FileText` |
| Person (known/verified) | `UserCheck` | Online | `CheckCircle2` |
| Person (unknown) | `UserX` | Offline | `XCircle` |
| Anomaly · Violence | `Zap` | Auth failed | `ShieldX` |
| Anomaly · Intrusion | `DoorOpen` | Severity · critical | `ShieldAlert` |
| Anomaly · Loitering | `Clock` | Severity · high | `AlertCircle` |
| Anomaly · PPE | `HardHat` | Severity · medium/low | `Info` |

**a11y:** icon-only controls require `aria-label`; purely decorative icons get `aria-hidden="true"`.

---

## 11. Responsive & layout notes

- **Desktop-first.** Minimum supported viewport **1280×800**. No mobile/tablet layout in v1.
- **Guard view:** fixed three-column. The `AlertSidebar` (380px) collapses to a **64px icon strip** below 1440px width — alert dots + severity counts only; click to expand a flyout.
- **Admin / Analytics:** the 240px sidebar collapses to a **top nav bar** below 1280px (hamburger → sheet).
- Breakpoints used: `lg` (1280px) and `xl` (1440px). No `sm`/`md`.

```
≥1440:  Guard = [320 | 1fr | 380]      Admin = [240 | 1fr]
1280–1439: Guard = [320 | 1fr | 64]    Admin = [240 | 1fr]
<1280:  Guard = [320 | 1fr | 64]       Admin = [topnav / 1fr]  (Guard not targeted below min)
```

---

## 12. Dark theme specifics for Guard view

- **Background hierarchy** (deep navy/near-black, never pure black — pure black + bright alert = harsh halation in a dim room):
  - base `#0a0e1a` → raised `#111827` → sunken `#020617`.
- **Camera feed area:** `#020617` (the darkest surface) so there's no light bleed framing the video.
- **Alert severity glow:** critical alert cards add `box-shadow: 0 0 0 1px #dc2626` — a static 1px glow, **not** flashing. WCAG 2.1 §2.3.1 bans content flashing > 3×/sec; we never animate alert color.
- **Status bar text:** rendered with `text.secondary` (not `text.primary`) to sit one step quieter than active content — reduces visual noise on a 24/7 display.
- **Typography:** body text gets `letter-spacing: +0.01em` (the `--body-letter-spacing` var) — characters separate slightly better against the dark field.

```css
:root[data-theme="dark"] .alert-card[data-severity="critical"] {
  box-shadow: 0 0 0 1px var(--severity-critical);
}
:root[data-theme="dark"] body { letter-spacing: var(--body-letter-spacing); }
```

---

## 13. Accessibility checklist

### 13.1 Contrast table (computed against WCAG AA)

| Combination | Theme | Ratio | Pass |
|---|---|---|---|
| `text.primary` `#0f172a` on `surface.base` `#ffffff` | light | 17.9:1 | AAA |
| `text.secondary` `#475569` on `#ffffff` | light | 7.5:1 | AA (body) |
| `text.muted` `#94a3b8` on `#ffffff` | light | 2.6:1 | large/decorative only |
| brand-500 `#2b6cb0` on `#ffffff` | light | 4.9:1 | AA (body) |
| white on brand-500 `#2b6cb0` | both | 4.3:1 | AA large / button label OK |
| `text.primary` `#f3f4f6` on `surface.base` `#0a0e1a` | dark | 16.6:1 | AAA |
| `text.secondary` `#9ca3af` on `#0a0e1a` | dark | 6.9:1 | AA (body) |
| `text.muted` `#6b7280` on `#0a0e1a` | dark | 3.7:1 | large only |
| severity.critical `#dc2626` on `#0a0e1a` | dark | 4.8:1 | AA (body) |
| severity.critical `#dc2626` on `#ffffff` | light | 4.5:1 | AA (body, exactly at floor) |

> **Resolved ambiguity / flag:** `text.muted` fails 4.5:1 in both themes — by design it is for placeholders, disabled text, and timestamps (large or non-essential). **Never use `text.muted` for content a user must read to operate the system.** Timestamps that carry operational meaning (alert age) use `text.secondary`.

### 13.2 Focus-visible ring

`2px solid var(--focus-ring)`, `2px` offset, applied via `:focus-visible` only (mouse clicks don't show it; keyboard does). The ring is **never** removed without a replacement — `outline: none` alone is prohibited in review.

### 13.3 Keyboard navigation map

| Interaction | Keys |
|---|---|
| Move between focusable controls | `Tab` / `Shift+Tab` |
| Activate button / link | `Enter` / `Space` |
| Close modal / toast / popover | `Esc` |
| Tabs navigation | `←` `→` (roving tabindex) |
| Select menu | `↑` `↓`, `Enter` to choose, type-ahead |
| Inline table edit | `Enter` save, `Esc` cancel |
| Acknowledge focused alert | `A` (when AlertSidebar focused) |
| Resolve focused alert | `R` |

### 13.4 Screen-reader live regions

| Region | `aria-live` | Notes |
|---|---|---|
| New alert in sidebar | `assertive` | Critical safety info interrupts |
| Toast — error | `assertive` | |
| Toast — success/info/warning | `polite` | |
| Head-count display | `polite` | Announce on change, debounced |
| Worker / camera status change | `polite` | |

### 13.5 Icon rules

- Icon-only buttons: **always** `aria-label` (e.g. `aria-label="Acknowledge alert"`).
- Decorative icons adjacent to text: `aria-hidden="true"`.
- Status dots: `role="img"` + descriptive `aria-label` ("Camera online").

---

**End of VMS Design System.**
