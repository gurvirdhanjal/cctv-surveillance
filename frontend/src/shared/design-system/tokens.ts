/**
 * Design system tokens — mirrors the CSS custom properties in index.css.
 * Use these in JS/TS contexts (tests, design-time tooling, Storybook).
 * Components should consume the Tailwind utilities (which reference the CSS vars)
 * rather than importing this file directly.
 */

export const brand = {
  50: '#eef6ff',
  100: '#d9eaff',
  300: '#7eb0ff',
  500: '#2b6cb0',
  700: '#1a4480',
  900: '#102a4c',
  950: '#0a1c33',
} as const

export const severity = {
  critical: '#dc2626',
  high: '#ea580c',
  medium: '#d97706',
  low: '#65a30d',
} as const

export const lightTheme = {
  text: {
    primary: '#0f172a',
    secondary: '#475569',
    muted: '#94a3b8',
    inverse: '#ffffff',
  },
  surface: {
    base: '#ffffff',
    raised: '#f8fafc',
    sunken: '#f1f5f9',
  },
  border: {
    default: '#e2e8f0',
    strong: '#cbd5e1',
  },
  focus: { ring: '#2b6cb0' },
  interactive: {
    hover: '#1a4480',
    active: '#102a4c',
    disabledBg: '#e2e8f0',
    disabledText: '#94a3b8',
  },
  destructive: {
    base: '#dc2626',
    hover: '#b91c1c',
    subtleBg: '#fef2f2',
  },
  status: {
    online: '#16a34a',
    offline: '#6b7280',
    authFailed: '#d97706',
    maintenance: '#2563eb',
  },
  success: '#16a34a',
  info: '#2563eb',
  warning: '#d97706',
  error: '#dc2626',
  selectedRow: '#eef6ff',
} as const

export const darkTheme = {
  text: {
    primary: '#f3f4f6',
    secondary: '#9ca3af',
    muted: '#6b7280',
    inverse: '#0f172a',
  },
  surface: {
    base: '#0a0e1a',
    raised: '#111827',
    sunken: '#020617',
  },
  border: {
    default: '#1f2937',
    strong: '#374151',
  },
  focus: { ring: '#7eb0ff' },
  interactive: {
    hover: '#3b82f6',
    active: '#2b6cb0',
    disabledBg: '#1f2937',
    disabledText: '#4b5563',
  },
  destructive: {
    base: '#dc2626',
    hover: '#ef4444',
    subtleBg: '#1f1315',
  },
  status: {
    online: '#22c55e',
    offline: '#9ca3af',
    authFailed: '#f59e0b',
    maintenance: '#3b82f6',
  },
  success: '#22c55e',
  info: '#3b82f6',
  warning: '#f59e0b',
  error: '#ef4444',
  selectedRow: '#0a1c33',
} as const

/** Motion durations — used for CSS transition values. */
export const motion = {
  fast: '120ms',
  base: '200ms',
  slow: '300ms',
  easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
} as const

/** Elevation shadows — matches the CSS vars in each theme block. */
export const elevation = {
  0: 'none',
  1: '0 1px 2px rgba(0,0,0,0.06)',
  2: '0 4px 6px rgba(0,0,0,0.10)',
  3: '0 10px 25px rgba(0,0,0,0.20)',
} as const

/** Typography scale — font-size in px, matching §3.1. */
export const typeScale = {
  displayXl: { size: 32, weight: 700, lineHeight: 38, letterSpacing: '-0.02em' },
  displayLg: { size: 28, weight: 700, lineHeight: 34, letterSpacing: '-0.02em' },
  displayMd: { size: 24, weight: 600, lineHeight: 30, letterSpacing: '-0.01em' },
  bodyLg: { size: 16, weight: 400, lineHeight: 24, letterSpacing: '0' },
  bodyMd: { size: 14, weight: 400, lineHeight: 20, letterSpacing: '0' },
  bodySm: { size: 13, weight: 400, lineHeight: 18, letterSpacing: '0' },
  labelXs: { size: 11, weight: 600, lineHeight: 14, letterSpacing: '0.06em' },
  monoMd: { size: 13, weight: 400, lineHeight: 18, letterSpacing: '0' },
  monoSm: { size: 12, weight: 400, lineHeight: 16, letterSpacing: '0' },
} as const
