import { Link, NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
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

function useAdminPageTitle(): string {
  const { pathname } = useLocation()
  const match = NAV_ITEMS.find(({ to, end }) =>
    end ? pathname === to : pathname.startsWith(to),
  )
  return match?.label ?? 'Admin'
}

export function AdminLayout() {
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const user = useAuthStore((s) => s.user)
  const pageTitle = useAdminPageTitle()

  return (
    <>
      <Helmet title={`${pageTitle} — Admin`} />
      <div className="flex h-screen flex-col overflow-hidden bg-surface-sunken">
        {/* ── Top bar ─────────────────────────────────────────────────────── */}
        <header className="flex h-12 flex-shrink-0 items-center gap-3 border-b border-border bg-surface-raised px-4">
          <Link
            to="/live"
            className="font-display text-[16px] font-bold text-brand-500 hover:text-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)] rounded-sm"
            aria-label="VMS — go to live view"
          >
            VMS
          </Link>
          <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-widest bg-brand-100 text-brand-700 select-none">
            Admin
          </span>
          <span
            className="h-4 w-px bg-[var(--border-default)] mx-0.5"
            aria-hidden="true"
          />
          <span className="text-[13px] font-medium text-text-primary">{pageTitle}</span>

          <div className="flex-1" />

          <Link
            to="/live"
            className="flex items-center gap-1 rounded-md px-2.5 py-1.5 text-[13px] text-text-secondary hover:text-text-primary hover:bg-surface-sunken transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
          >
            <svg
              className="h-3.5 w-3.5"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              aria-hidden="true"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Live
          </Link>

          {user && (
            <span className="rounded bg-surface-sunken px-2 py-1 text-[11px] font-medium text-text-muted uppercase tracking-wide select-none">
              {user.role}
            </span>
          )}

          <button
            type="button"
            onClick={() => {
              logout()
              navigate('/login', { replace: true })
            }}
            className="rounded-md px-3 py-1.5 text-[13px] text-text-muted hover:text-text-primary hover:bg-surface-sunken transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
          >
            Sign out
          </button>
        </header>

        {/* ── Body: sidebar + content ──────────────────────────────────────── */}
        <div className="flex flex-1 min-h-0">
          <nav
            aria-label="Admin navigation"
            className="w-52 shrink-0 overflow-y-auto border-r border-border bg-surface-raised py-3"
          >
            {NAV_ITEMS.map(({ to, label, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `block px-4 py-2 text-[14px] transition-colors ${
                    isActive
                      ? 'bg-brand-100 text-brand-700 font-medium'
                      : 'text-text-secondary hover:text-text-primary hover:bg-surface-sunken'
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
      </div>
    </>
  )
}
