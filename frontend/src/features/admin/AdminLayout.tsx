import { Link, NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { motion } from 'framer-motion'
import {
  LayoutDashboard,
  Camera,
  Users,
  MapPin,
  Zap,
  Bell,
  Wrench,
  Cpu,
  UserCog,
  FileText,
  LogOut,
  ExternalLink,
} from 'lucide-react'

function VmsLogo() {
  return (
    <div
      className="animate-logo-glow flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--brand-accent)]/30 bg-[#120504]"
      aria-hidden="true"
    >
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <circle cx="9" cy="9" r="7.5" stroke="var(--brand-accent)" strokeWidth="0.75" />
        <circle cx="9" cy="9" r="3.75" stroke="var(--brand-accent)" strokeWidth="0.75" />
        <circle cx="9" cy="9" r="1.25" fill="var(--brand-accent)" />
        <rect x="8.25" y="0.75" width="1.5" height="1.75" rx="0.5" fill="var(--brand-accent)" />
        <rect x="8.25" y="15.5" width="1.5" height="1.75" rx="0.5" fill="var(--brand-accent)" />
        <rect x="0.75" y="8.25" width="1.75" height="1.5" rx="0.5" fill="var(--brand-accent)" />
        <rect x="15.5" y="8.25" width="1.75" height="1.5" rx="0.5" fill="var(--brand-accent)" />
      </svg>
    </div>
  )
}
import { useAuthStore } from '@/stores/authStore'
import { useRouteTheme } from '@/hooks/useRouteTheme'

interface NavItem {
  to: string
  label: string
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' | 'false' }>
  end: boolean
}

interface NavSection {
  group: string
  items: NavItem[]
}

const NAV_SECTIONS: NavSection[] = [
  {
    group: 'Monitoring',
    items: [
      { to: '/admin', label: 'Dashboard', icon: LayoutDashboard, end: true },
      { to: '/admin/cameras', label: 'Cameras', icon: Camera, end: false },
    ],
  },
  {
    group: 'People',
    items: [
      { to: '/admin/persons', label: 'Persons', icon: Users, end: false },
      { to: '/admin/zones', label: 'Zones', icon: MapPin, end: false },
    ],
  },
  {
    group: 'Operations',
    items: [
      { to: '/admin/anomaly-detectors', label: 'Anomaly Detectors', icon: Zap, end: false },
      { to: '/admin/alert-routing', label: 'Alert Routing', icon: Bell, end: false },
      { to: '/admin/maintenance', label: 'Maintenance', icon: Wrench, end: false },
    ],
  },
  {
    group: 'System',
    items: [
      { to: '/admin/models', label: 'Models', icon: Cpu, end: false },
      { to: '/admin/users', label: 'Users', icon: UserCog, end: false },
      { to: '/admin/audit', label: 'Audit Log', icon: FileText, end: false },
    ],
  },
]

const ALL_ITEMS = NAV_SECTIONS.flatMap((s) => s.items)

function useAdminPageTitle(): string {
  const { pathname } = useLocation()
  const match = ALL_ITEMS.find(({ to, end }) =>
    end ? pathname === to : pathname.startsWith(to),
  )
  return match?.label ?? 'Admin'
}

export function AdminLayout() {
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const user = useAuthStore((s) => s.user)
  const pageTitle = useAdminPageTitle()

  useRouteTheme('light')

  return (
    <>
      <Helmet title={`${pageTitle} — Admin`} />
      <div className="flex h-screen overflow-hidden">
        {/* ── Light sidebar ────────────────────────────────────────────────── */}
        <aside className="flex w-60 flex-shrink-0 flex-col overflow-hidden border-r border-border bg-surface-raised">
          {/* Brand header */}
          <div className="flex h-14 flex-shrink-0 items-center gap-3 border-b border-border px-4">
            <VmsLogo />
            <span className="font-display text-[15px] font-bold tracking-tight text-text-primary">
              VMS
            </span>
            <span className="ml-auto shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-surface-sunken text-text-muted select-none">
              Admin
            </span>
          </div>

          {/* Navigation */}
          <nav aria-label="Admin navigation" className="flex-1 overflow-y-auto py-2">
            {NAV_SECTIONS.map((section) => (
              <div key={section.group}>
                <p className="mt-4 mb-1 px-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted select-none">
                  {section.group}
                </p>
                {section.items.map(({ to, label, icon: Icon, end }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={end}
                    className={({ isActive }) =>
                      `relative mx-2 flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] font-medium transition-colors duration-fast ${
                        isActive
                          ? 'text-text-primary'
                          : 'text-text-secondary hover:bg-surface-sunken hover:text-text-primary'
                      }`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && (
                          <motion.span
                            layoutId="admin-nav-active"
                            className="absolute inset-0 rounded-md bg-surface-sunken"
                            style={{ borderLeft: '3px solid var(--brand-accent)' }}
                            transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                          />
                        )}
                        <Icon className="relative h-[15px] w-[15px] shrink-0" aria-hidden="true" />
                        <span className="relative">{label}</span>
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>

          {/* Sidebar footer */}
          <div className="flex-shrink-0 border-t border-border p-2 space-y-0.5">
            <Link
              to="/live"
              className="flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] text-text-secondary transition-colors hover:bg-surface-sunken hover:text-text-primary"
            >
              <ExternalLink className="h-[15px] w-[15px] shrink-0" aria-hidden="true" />
              Live View
            </Link>
            <button
              type="button"
              onClick={() => {
                logout()
                navigate('/login', { replace: true })
              }}
              className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-[13px] text-text-secondary transition-colors hover:bg-surface-sunken hover:text-text-primary"
            >
              <LogOut className="h-[15px] w-[15px] shrink-0" aria-hidden="true" />
              Sign out
            </button>
          </div>
        </aside>

        {/* ── Main area ─────────────────────────────────────────────────────── */}
        <div className="flex min-w-0 flex-1 flex-col bg-surface-sunken">
          {/* Top bar */}
          <header className="flex h-14 flex-shrink-0 items-center border-b border-border bg-surface-base px-6">
            <span
              className="text-[15px] font-semibold text-text-primary"
              aria-hidden="true"
            >
              {pageTitle}
            </span>
            <div className="flex-1" />
            {user && (
              <span className="rounded-full bg-surface-sunken px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-text-muted select-none">
                {user.role}
              </span>
            )}
          </header>

          <main className="min-w-0 flex-1 overflow-auto">
            <Outlet />
          </main>
        </div>
      </div>
    </>
  )
}
