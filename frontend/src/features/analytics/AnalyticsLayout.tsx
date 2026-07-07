import { NavLink, Outlet } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'

const NAV = [
  { to: '/analytics', label: 'Dashboard', end: true },
  { to: '/analytics/timeline', label: 'Timeline', end: false },
  { to: '/analytics/heatmap', label: 'Heatmap', end: false },
]

export function AnalyticsLayout() {
  return (
    <div data-theme="light" className="flex min-h-screen bg-surface-base">
      <Helmet titleTemplate="%s — Analytics" />
      <nav
        aria-label="Analytics navigation"
        className="w-56 shrink-0 border-r border bg-surface-raised p-4"
      >
        <p className="mb-4 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
          Analytics
        </p>
        <ul className="space-y-0.5">
          {NAV.map(({ to, label, end }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={end}
                className={({ isActive }) =>
                  [
                    'block rounded-md py-2 text-[14px] transition-colors duration-fast border-l-[3px]',
                    isActive
                      ? 'border-[var(--brand-accent)] bg-surface-sunken font-medium text-text-primary pl-[calc(0.75rem_-_3px)] pr-3'
                      : 'border-transparent px-3 text-text-secondary hover:bg-surface-sunken',
                  ].join(' ')
                }
              >
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="mt-6 border-t border pt-4">
          <NavLink
            to="/forensic"
            className="block rounded-md px-3 py-2 text-[14px] text-text-secondary transition-colors hover:bg-surface-sunken"
          >
            Forensic Search
          </NavLink>
        </div>
      </nav>
      <main className="flex-1 overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  )
}
