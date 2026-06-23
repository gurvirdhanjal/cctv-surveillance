# Frontend Documentation

Two documents. Each owns a distinct concern. Read both before implementing any frontend feature.

---

## [`2026-05-01-vms-frontend-spec.md`](2026-05-01-vms-frontend-spec.md)

**Frontend Specification — architecture, features, API surface**

Owns:
- Tech stack choices and rationale
- Route table and role guards
- `frontend/` file layout
- Backend prerequisites (which API endpoints must exist)
- Feature behavior per view (Guard, Analytics, Admin)
- Real-time Socket.io event contract
- Zustand state shape
- Form validation rules
- Table virtualisation
- Performance budgets (bundle size, LCP, TTI, CLS)
- Error boundary hierarchy and API error mapping
- i18n strategy
- Testing strategy (Vitest + RTL + Playwright)
- Build and dev tooling
- Phase 4 sub-plan decomposition

---

## [`2026-06-24-vms-design-system.md`](2026-06-24-vms-design-system.md)

**Design System — visual contract**

Owns:
- Color palette (both themes, all semantic tokens)
- CSS custom property definitions
- Theme toggle implementation (`themeStore`, `useRouteTheme`, `ThemeProvider`)
- Typography scale (Inter Display / Inter / JetBrains Mono)
- Spacing and layout grid
- Elevation system
- Component design patterns (Button, Input, Badge, Card, Alert card, Table, Modal, Toast, Tooltip, Tabs, Camera tile, Person dot, etc.)
- Form UX patterns (wizard, inline edit, soft-delete, GDPR purge)
- Motion and animation (keyframes, reduced-motion rules)
- Iconography (Lucide React semantic map)
- Accessibility (contrast tables, keyboard nav map, live-region spec)
- Dark theme specifics for Guard view

---

## Rule

When the two documents disagree on a visual matter (color value, token name, component state), **the design system wins**.

When they disagree on a behavioral matter (route, API call, state shape, event payload), **the frontend spec wins**.
