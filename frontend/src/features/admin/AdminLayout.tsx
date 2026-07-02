import { NavLink, Outlet } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'

const NAV_ITEMS = [
  { to: '/admin', label: 'Dashboard', end: true },
  { to: '/admin/persons', label: 'Persons', end: false },
  { to: '/admin/cameras', label: 'Cameras', end: false },
  { to: '/admin/zones', label: 'Zones', end: false },
  { to: '/admin/users', label: 'Users', end: false },
  { to: '/admin/maintenance', label: 'Maintenance', end: false },
  { to: '/admin/anomaly-detectors', label: 'Anomaly Detectors', end: false },
  { to: '/admin/alert-routing', label: 'Alert Routing', end: false },
  { to: '/admin/models', label: 'Models', end: false },
  { to: '/admin/audit', label: 'Audit Log', end: false },
]

export function AdminLayout() {
  return (
    <>
      <Helmet title="Admin" />
      <div className="flex min-h-screen bg-surface-sunken">
        <nav
          aria-label="Admin navigation"
          className="w-56 shrink-0 bg-surface-elevated border-r border-border-subtle flex flex-col py-4"
        >
          <p className="px-4 mb-4 text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">
            Admin
          </p>
          {NAV_ITEMS.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `px-4 py-2 text-[14px] transition-colors ${
                  isActive
                    ? 'bg-brand-100 text-brand-700 font-medium'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <main className="flex-1 min-w-0 overflow-auto">
          <Outlet />
        </main>
      </div>
    </>
  )
}
