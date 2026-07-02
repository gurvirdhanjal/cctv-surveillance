import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { useAuthStore } from '@/stores/authStore'

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
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const user = useAuthStore((s) => s.user)

  return (
    <>
      <Helmet title="Admin" />
      <div className="flex min-h-screen bg-surface-sunken">
        <nav
          aria-label="Admin navigation"
          className="w-56 shrink-0 bg-surface-raised border-r border-border flex flex-col py-4"
        >
          <div className="px-4 mb-4 flex items-center justify-between">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
              Admin
            </p>
            <Link
              to="/live"
              className="text-[12px] text-text-muted hover:text-brand-500"
              aria-label="Go to live view"
            >
              Live &rarr;
            </Link>
          </div>
          {NAV_ITEMS.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `px-4 py-2 text-[14px] transition-colors ${
                  isActive
                    ? 'bg-brand-100 text-brand-700 font-medium'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-sunken'
                }`
              }
            >
              {label}
            </NavLink>
          ))}

          <div className="mt-auto pt-4 border-t border-border mx-4">
            {user && (
              <p className="text-[11px] text-text-muted mb-2 truncate">
                {user.role} · {user.userId}
              </p>
            )}
            <button
              type="button"
              onClick={() => {
                logout()
                navigate('/login', { replace: true })
              }}
              className="w-full text-left px-0 py-1 text-[13px] text-text-muted hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
            >
              Sign out
            </button>
          </div>
        </nav>
        <main className="flex-1 min-w-0 overflow-auto">
          <Outlet />
        </main>
      </div>
    </>
  )
}
