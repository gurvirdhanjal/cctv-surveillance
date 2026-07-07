# VMS Design System
**Design Specification** · 2026-06-24 (updated 2026-07-06 — crimson brand refresh)
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

### 2.0 Three-tier color model (binding rule)

Surveillance software lives with red = alarm. This is non-negotiable — Honeywell is red, Hikvision is red, but their *software* is not. Their logo is red. Their buttons are not.

**Tier 1 — Brand Identity.** Crimson (`brand-500 = #c0392b`). Appears on ≤ 5 elements per screen: the logo/wordmark, the 3px left-border on the active navigation item, and a thin accent on the sidebar header. Never on buttons, focus rings, selections, or table rows.

**Tier 2 — Action / Interactive.** Dark Charcoal (`action-700 = #1e293b`). Appears on all interactive controls: primary buttons, focus rings, toggle fills. Neutral, professional, reads as "this is how you act."

**Tier 3 — Alarm / Severity.** Signal Red (`#dc2626`). Appears ONLY on alarm severity indicators: critical badge, critical card left-border, recording-failure badge, device-fault badge. It must never be diluted by appearing anywhere else — its exclusivity is what makes it scannable in a dim control room.

This separation prevents the "red means alarm" ambiguity that degrades operator response time.

### 2.1 Brand & severity (theme-invariant)

```ts
// Brand — Crimson scale (ACCENT ONLY — see §2.0)
brand: {
  50:  '#fff1f0',  // very subtle hover well (rarely needed)
  100: '#ffe4e1',  // light brand bg (avoid in production)
  500: '#c0392b',  // ACCENT — logo, nav active left-bar, NOTHING ELSE
  700: '#9b2226',  // hover on brand-accented elements only
  950: '#3b0a0a',  // dark-theme context (nav dark area accent)
}

// Action — Dark Charcoal scale (PRIMARY INTERACTIVE)
action: {
  600: '#334155',  // secondary action bg on hover
  700: '#1e293b',  // primary button fill, toggle fill — THIS is the interactive color
  800: '#0f172a',  // primary button hover
  900: '#020617',  // primary button pressed
}

severity: { critical:'#dc2626', high:'#ea580c', medium:'#d97706', low:'#65a30d' }
```

Severity hex values are identical in both themes — a critical red must mean the same thing on any display. Contrast is managed by the surface behind them, not by re-tinting the severity color.

> **Three-tier color rule — see §2.0. Brand ≠ Action ≠ Alarm. They are always distinct.**

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

> **Light theme surfaces are neutral white/slate — not warm-tinted.** The brand identity (crimson) is expressed through the nav active bar and logo, not through surface color. Warm-tinted surfaces would create ambient red saturation that competes with the alarm semantic. Keep surfaces clean.

### 2.3 Interactive states

| Token | Light | Dark | Use |
|---|---|---|---|
| `interactive.primary` | `#1e293b` | — | Primary button fill (action-700; dark uses existing dark bg) |
| `focus.ring` | `#1e293b` | `#94a3b8` | `:focus-visible` outline — charcoal on light, light-gray on dark |
| `interactive.hover` | `#0f172a` | `#3b82f6` | Primary button hover (action-800) |
| `interactive.active` | `#020617` | `#2b6cb0` | Primary button pressed (action-900) |
| `brand.accent` | `#c0392b` | `#c0392b` | Nav active left-bar, logo — accent only |
| `interactive.disabledBg` | `#e2e8f0` | `#1f2937` | Disabled control fill |
| `interactive.disabledText` | `#94a3b8` | `#4b5563` | Disabled control label |
| `destructive.base` | `#dc2626` | `#dc2626` | Delete / purge fill |
| `destructive.hover` | `#b91c1c` | `#ef4444` | Destructive hover |
| `destructive.subtleBg` | `#fef2f2` | `#1f1315` | Destructive modal body tint |

> **Focus ring:** charcoal (`#1e293b`) on light surfaces achieves ~15:1 contrast on white — AAA. On dark surfaces, `#94a3b8` (slate-400) achieves sufficient contrast without using the crimson brand. Never use `brand-accent` as the focus ring — brand appears on structure, not interactive focus.

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
| `selected.row` | `#f1f5f9` (surface-sunken) | `#0a1c33` | TanStack table selected row |

> **Selected row uses neutral surface-sunken**, not a brand-tinted color. Putting crimson in a selection highlight would scatter the alarm semantic across every table. The neutral tint is sufficient — it creates visible selection without color noise.

---

### 2.7 Three-tier color rule — enforcement

**Quick decision table:**

| What am I styling? | Correct color | Wrong colors |
|---|---|---|
| Primary button, toggle, checkbox, slider | `action-700` (#1e293b) | brand-500, severity-critical |
| Focus ring | `--focus-ring` (#1e293b light / #94a3b8 dark) | brand-500, severity-critical |
| Selected table row | `surface-sunken` (#f1f5f9) | brand-50, any red tint |
| Active navigation item FILL | `surface-sunken` or `white/5` — subtle | brand-500 fill |
| Active navigation INDICATOR | `brand-500` as a 3px left border | action-700, severity |
| Logo / wordmark | `brand-500` | action-700, severity |
| Critical alarm badge | `severity-critical` (#dc2626) | brand-500, action-700 |
| Critical alarm left-border | `severity-critical` (#dc2626) | brand-500, action-700 |
| Recording failure, device fault | `severity-critical` (#dc2626) | brand-500, action-700 |
| Camera health score bar | `action-700` | brand-500, severity |
| SLA warning/breach | `amber-500` | red, brand-500 |

If you are unsure: **ask "is this an alarm signal?"** → yes → severity. **"Is this a button/control?"** → yes → action. **"Is this a logo or nav active bar?"** → yes → brand.

---

### 2.8 Forbidden token names

These names **do not exist** in the design system. Using them is a type error and a design lint failure:

| WRONG — do not use | CORRECT equivalent |
|---|---|
| `surface-elevated` | `surface-raised` |
| `border-subtle` | `border` (maps to `--border-default`) |
| `border-muted` | `border` |
| `text-tertiary` | `text-muted` |
| `surface-hover` | `surface-raised` (nav hover) or `surface-sunken` (table row hover) |
| `brand-primary` | `brand-500` |
| `brand-secondary` | `brand-700` |
| `color-brand` | `brand-500` |

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
/* index.css — updated 2026-07-06: three-tier color model */

/* Duration tokens — theme-invariant */
:root {
  --duration-fast:     100ms;
  --duration-quick:    120ms;
  --duration-base:     180ms;
  --duration-slow:     200ms;
  --duration-flash:    600ms;
  --easing-standard:   cubic-bezier(0.4, 0, 0.2, 1);
  --easing-emphasized: cubic-bezier(0.2, 0, 0, 1);
}

:root[data-theme="light"] {
  --text-primary:   #0f172a;
  --text-secondary: #475569;
  --text-muted:     #94a3b8;
  --text-inverse:   #ffffff;

  --surface-base:   #ffffff;
  --surface-raised: #f8fafc;  /* neutral slate-50 */
  --surface-sunken: #f1f5f9;  /* neutral slate-100 */

  --border-default: #e2e8f0;  /* neutral slate-200 */
  --border-strong:  #cbd5e1;  /* neutral slate-300 */

  /* Action (primary interactive) — charcoal, NOT brand red */
  --interactive-primary: #1e293b;  /* action-700 — primary button fill */
  --interactive-hover:   #0f172a;  /* action-800 */
  --interactive-active:  #020617;  /* action-900 */
  --focus-ring:          #1e293b;  /* charcoal — neutral, not red */

  /* Brand accent — sparse identity only */
  --brand-accent: #c0392b;         /* nav active left-bar, logo */

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
  --selected-row:  #f1f5f9;  /* neutral surface-sunken — never a red tint */

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
  --selected-row:  #450a0a;  /* brand-950 deep crimson-black */

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
// tailwind.config.ts (excerpt) — updated 2026-07-06: three-tier color model
extend: {
  colors: {
    text: { primary: 'var(--text-primary)', secondary: 'var(--text-secondary)', muted: 'var(--text-muted)', inverse: 'var(--text-inverse)' },
    surface: { base: 'var(--surface-base)', raised: 'var(--surface-raised)', sunken: 'var(--surface-sunken)' },
    border: { DEFAULT: 'var(--border-default)', strong: 'var(--border-strong)' },
    severity: { critical: 'var(--severity-critical)', high: 'var(--severity-high)', medium: 'var(--severity-medium)', low: 'var(--severity-low)' },
    // brand — ACCENT only (logo, nav active bar — see §2.0 and §2.7)
    brand: {
      50:  '#fff1f0',
      100: '#ffe4e1',
      500: '#c0392b',  // accent — nav left-bar, logo only
      700: '#9b2226',
      950: '#3b0a0a',
    },
    // action — PRIMARY INTERACTIVE (buttons, focus, toggles — see §2.0)
    action: {
      600: '#334155',   // secondary hover bg
      700: '#1e293b',   // primary fill
      800: '#0f172a',   // hover
      900: '#020617',   // pressed
    },
  },
  boxShadow: { 1: 'var(--shadow-1)', 2: 'var(--shadow-2)', 3: 'var(--shadow-3)' },
  transitionDuration: {
    fast:  'var(--duration-fast)',    // 100ms — hover
    quick: 'var(--duration-quick)',   // 120ms — dropdown
    base:  'var(--duration-base)',    // 180ms — modal, sidebar
    slow:  'var(--duration-slow)',    // 200ms — toast
  },
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
  light: '#ffffff',   // matches --surface-base light (pure white, unchanged)
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
// primary / md — uses action-700 (dark charcoal), NOT brand-500 (crimson)
<button
  className="inline-flex h-10 items-center gap-2 rounded-[10px] bg-action-700 px-4
             text-14 font-600 text-text-inverse shadow-1
             hover:bg-action-800 active:bg-action-900
             focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2
             focus-visible:outline-[var(--focus-ring)]
             aria-disabled:pointer-events-none aria-disabled:bg-[var(--disabled-bg)]
             aria-disabled:text-[var(--disabled-text)]"
>
  {loading ? <Spinner size={16} /> : <Icon size={20} aria-hidden="true" />}
  Save
</button>
```

> **Why `action-700` not `brand-500`:** See §2.0. Primary buttons use the action (charcoal) tier, not the brand (crimson) tier. Crimson is reserved for the nav active indicator and logo.

```
secondary:   border border-strong bg-transparent text-text-primary hover:bg-surface-sunken
ghost:       bg-transparent text-text-primary hover:bg-surface-sunken
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
focused:     ring-2 ring-brand-500 shadow-2  /* brand-500 = #c0392b crimson */
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
.person-dot[data-identity="known"]    { background: #c0392b; }  /* brand-500 crimson */
.person-dot[data-identity="unknown"]  { background: #ef4444; }  /* bright red — visually distinct from brand */
.person-dot[data-identity="followed"] { background: #facc15; }  /* yellow — always distinct */
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

**Cardinal rule: never animate live telemetry.** Camera feeds, head-count numbers, FPS counters, person dots — these update in real time. Animating their transitions obscures changes rather than highlighting them. Motion is reserved for navigation and structural UI transitions.

### 9.0 Duration table

| Interaction | Duration | Why |
|---|---|---|
| Hover state (color, shadow) | 100ms | Feels instant; longer = sluggish |
| Dropdown / popover appear | 120ms | Opacity + 4px translateY |
| Page fade transition | 120ms | Opacity only; no slide |
| Accordion expand/collapse | 150ms | Height transition |
| Sidebar open/close | 180ms | Emphasized slide |
| Modal enter | 180ms | Scale 0.96 → 1 + opacity |
| Toast slide-in | 200ms | From right |
| Card hover shadow | 100ms | Shadow-1 → shadow-2 |
| Tab indicator slide | 200ms | Sliding underline |
| Skeleton → content | 0ms | Instant swap — no fade |
| Chart initial render | 0ms | Never animate chart data |
| Chart data refresh | 0ms | Instant update |
| Live telemetry values | 0ms | Head count, FPS, bitrate — instant |
| Alert severity flash | 600ms one-shot | Background only, not a pulse |

Durations: `fast 100ms` · `quick 120ms` · `base 180ms` · `slow 200ms`. Easings: `standard cubic-bezier(0.4,0,0.2,1)`, `emphasized cubic-bezier(0.2,0,0,1)`.

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
| action-700 `#1e293b` on `#ffffff` | light | **15.2:1** | AAA — primary button fill |
| white on action-700 `#1e293b` | light | **15.2:1** | AAA — button label |
| brand-500 `#c0392b` on `#ffffff` | light | 4.6:1 | AA — accent use (nav bar) only |
| `text.primary` `#f3f4f6` on `surface.base` `#0a0e1a` | dark | 16.6:1 | AAA |
| `text.secondary` `#9ca3af` on `#0a0e1a` | dark | 6.9:1 | AA (body) |
| `text.muted` `#6b7280` on `#0a0e1a` | dark | 3.7:1 | large only |
| severity.critical `#dc2626` on `#0a0e1a` | dark | 4.8:1 | AA (body) |
| severity.critical `#dc2626` on `#ffffff` | light | 4.5:1 | AA (body, exactly at floor) |
| severity.critical `#dc2626` on `surface.sunken` `#fff5f5` | light | 4.4:1 | close to floor — use on base/raised surfaces, not sunken |

> **Resolved ambiguity / flag:** `text.muted` fails 4.5:1 in both themes — by design it is for placeholders, disabled text, and timestamps (large or non-essential). **Never use `text.muted` for content a user must read to operate the system.** Timestamps that carry operational meaning (alert age) use `text.secondary`.

> **New contrast flag (2026-07-06):** The warm `surface.sunken` (`#fff5f5`) reduces severity-critical's contrast to 4.4:1 — just below AA. Severity-critical badges and borders should always be placed on `surface.base` (`#ffffff`) or `surface.raised` (`#fffbfb`), not on `surface.sunken`. This is a table-header / inset-well color — alert content does not appear there anyway.

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

## §14. Enterprise VMS Design Principles

> Distilled from the product-specific rulebook (2026-07-02). These rules are **binding** — they override aesthetic preference wherever they conflict with earlier sections.

### 14.1 Philosophy

The UI must communicate: **reliable · security-focused · fast · industrial · operational · data-dense without clutter**.

Avoid: playful styling, excessive animations, oversized controls, consumer-app rounding. A VMS is closer to a control room than a marketing website.

### 14.2 8-Point Grid — Mandatory

All spacing must land on the 4px base unit. Preferred stops (in px):

| Token | px |
|---|---|
| t-1 | 4 |
| t-2 | 8 |
| t-4 | 16 |
| t-6 | 24 |
| t-8 | 32 |
| t-12 | 48 |
| t-16 | 64 |

**Never invent spacing like 13 px or 27 px.** Common layout values:

| Context | Value |
|---|---|
| Page padding | 24 px (p-6) |
| Card padding | 24 px (p-6) |
| Gap between cards | 16 px (gap-4) |
| Section margin | 32 px (mb-8) |
| Button horizontal padding | 16 px (px-4) |
| Sidebar padding | 24 px (px-6) |

### 14.3 Border Radius — Consistent Table

Never mix radius values arbitrarily. Use only these:

| Element | Value | Tailwind |
|---|---|---|
| Cards | 12 px | `rounded-xl` |
| Buttons | 10 px | `rounded-[10px]` |
| Inputs / Selects | 10 px | `rounded-[10px]` |
| Image / thumbnail | 10 px | `rounded-[10px]` |
| Badges / pills | 9999 px | `rounded-full` |
| Modals / dialogs | 12 px | `rounded-xl` |
| Sidebar nav items | 8 px | `rounded-lg` |
| Icon chip / KPI accent | 12 px | `rounded-xl` |

### 14.4 Shadow Scale

Never use heavy shadows. Two levels only:

| Context | Value |
|---|---|
| Default card | `box-shadow: 0 1px 2px rgba(0,0,0,.05)` → `var(--shadow-1)` |
| Hovered card | `box-shadow: 0 4px 12px rgba(0,0,0,.08)` → `var(--shadow-2)` |

### 14.5 Animation Durations

| Interaction | Duration |
|---|---|
| Hover state change | 120 ms |
| Modal enter/exit | 180 ms |
| Sidebar open/close | 180 ms |
| Dropdown appear | 120 ms |
| Card hover shadow | 120 ms |
| Toast slide-in | 200 ms |

Nothing longer than 250 ms. All animations must respect `prefers-reduced-motion`.

### 14.6 Camera Operational Status — 12 States

Replace the legacy 4-state model with operational language. These are mutually exclusive states; ordered by operational priority.

| State | Label | Color | Icon | Pulse | Description |
|---|---|---|---|---|---|
| `recording` | Recording | green-600 | `Radio` | Yes | Writing to storage + AI running |
| `streaming` | Streaming | green-500 | `Play` | Yes | Streaming to viewers; storage paused |
| `connected` | Connected | green-400 | `CheckCircle2` | No | Reachable, not yet streaming |
| `analytics` | Analytics | blue-500 | `Cpu` | No | AI pipeline active; stream degraded |
| `maintenance` | Maintenance | blue-400 | `Calendar` | No | Scheduled maintenance window active |
| `standby` | Standby | gray-400 | `Moon` | No | Healthy but idle |
| `reconnecting` | Reconnecting | amber-500 | `RefreshCw` | Yes | Connection lost; retrying |
| `unauthorized` | Unauthorized | amber-600 | `ShieldX` | No | RTSP credentials rejected |
| `unreachable` | Unreachable | gray-500 | `WifiOff` | No | No network path; not retrying |
| `offline` | Offline | gray-500 | `XCircle` | No | Gracefully stopped |
| `recovering` | Recovering | amber-400 | `Activity` | Yes | Reconnected; restarting pipeline |
| `disabled` | Disabled | gray-300 | `MinusCircle` | No | Manually disabled by admin |

**Pulse:** active only on `recording`, `streaming`, `reconnecting`, `recovering`. Never on alarm/warning states.

**Status language principle** — never use vague terms:

| Avoid | Use instead |
|---|---|
| Online | Recording · Streaming · Connected |
| Offline | Offline · Unreachable · Disabled |
| Healthy | Recording · Connected |
| Ready | Streaming |
| Error | Unauthorized · Unreachable + error code |
| Auth Failed | Unauthorized |
| Degraded | Reconnecting · Recovering |

### 14.7 Camera Card — Required Content

Every camera card must display at minimum:

- 16:9 snapshot thumbnail (lazy-loaded, `rounded-[10px]`)
- Status badge overlay (5-state from §14.6) with live pulse for Online
- Capability tier badge (FULL / MID / LOW)
- Profile metadata (FPS · Resolution) when `profile_data` is available
- AI capability summary ("Face · Body · Anomaly")
- Actions: **Live** (primary) · **Settings** (secondary) · **Delete** (icon, destructive, least prominent)

Delete must never share equal visual weight with Live or Settings.

### 14.8 Dashboard Data Density

The admin dashboard must display enough data for an operator to assess system state at a glance, without opening any sub-page:

**Required sections:**
1. Service health (API, DB, Redis, version)
2. KPI overview (Head Count, Cameras Online, Active Alerts)
3. Alert breakdown by type (Intrusion, Violence, Unknown Person, Loitering, PPE)
4. Camera health summary (total, online, offline, needs calibration)
5. Quick access links to primary admin sections

### 14.9 Empty States

Every empty state must use the `<EmptyState>` shared component. Never use plain text.

```
[Icon — 40px, text-text-muted opacity-40]
[Primary line — text-[15px] font-semibold text-text-primary mt-4]
[Secondary line — text-[13px] text-text-muted mt-1 max-w-xs]
[Optional CTA button — mt-5, primary variant]
centered, py-16
```

Examples:

```
Camera icon (40px, muted)
No cameras assigned
Assign cameras to begin monitoring live feeds.
[ Add Camera ]  ← primary button
```

```
Shield icon
No active alarms
The system is monitoring. Alarms will appear here.
(no CTA — this is a good state)
```

```
User icon
No persons enrolled
Enroll persons to enable facial recognition.
[ Enroll Person ]
```

```
FileText icon
No audit events found
Try adjusting the date range or filters.
[ Clear Filters ]  ← ghost button
```

**Rules:**
- Icon must be contextually relevant to what is missing (Camera for cameras, not a generic X)
- Primary line: specific. Not "No items" — "No cameras assigned."
- Secondary line: explains what to do, not what the absence means. Not "No cameras found" — "Assign cameras to begin monitoring."
- CTA: only if there is a direct action available. No CTA for read-only states or "good" states like no alarms.
- Never show a spinner and an empty state together.

### 14.10 Input Standards

Every text/number input must have:
- Height: `h-10` (40 px)
- Radius: `rounded-[10px]`
- Padding: `px-3`
- Border: `border border-border`
- Focus: `focus:border-brand-500 focus:outline-none` (brand-500 is now crimson `#c0392b`)
- Label: **above the input**, never inside as placeholder

### 14.11 Typography Hierarchy — Admin Pages

| Role | Size | Weight | Class |
|---|---|---|---|
| Page title (h1) | 22 px | 700 | `text-[22px] font-bold` |
| Section label | 11 px | 600 uppercase | `text-[11px] font-semibold uppercase tracking-[0.08em]` |
| Card title | 14 px | 600 | `text-[14px] font-semibold` |
| Body / table row | 13–14 px | 400–500 | `text-[13px]` or `text-[14px]` |
| Badge / meta | 11–12 px | 500–600 | `text-[11px]` or `text-[12px]` |
| Mono data (IDs, hashes) | 13 px mono | 400 | `font-mono text-[13px]` |

---

---

## 15. Change log

| Date | Change | Plan ref |
|---|---|---|
| 2026-06-24 | Initial design system: blue brand, component patterns, 8-pt grid, §14 enterprise principles | Phase 4 |
| 2026-07-06 | **Three-tier color model** — brand (crimson accent, logo+nav only), action (dark charcoal, all interactive), alarm (bright red, exclusive to severity). New `action` Tailwind scale. Surfaces reverted to neutral. Focus ring → charcoal. Expanded §2.0, §2.7, §9 (motion table), §14.6 (12-state camera status model), §14.9 (empty state component), §2.8 (forbidden tokens), §15 (change log). Phase 5 Enterprise Interaction Guidelines spec created. | Phase 4I + 5 (`2026-07-06-vms-phase4i-design-refresh.md`, `2026-07-06-vms-enterprise-interaction-guidelines.md`) |

**End of VMS Design System.**
