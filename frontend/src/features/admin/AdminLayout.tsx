import { useState } from 'react'
import { Link, NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard,
  Camera,
  MapPin,
  Zap,
  Wrench,
  Cpu,
  UserCog,
  LogOut,
  ExternalLink,
} from 'lucide-react'
import { Icon } from '@/shared/design-system/icons'
import { ProfileDialog } from '@/shared/workspace/ProfileDialog'
import { useAuthStore } from '@/stores/authStore'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarInset,
} from '@/shared/design-system/components/ui/sidebar'

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
      { to: '/admin/persons', label: 'Persons', icon: Icon.users, end: false },
      { to: '/admin/zones', label: 'Zones', icon: MapPin, end: false },
    ],
  },
  {
    group: 'Operations',
    items: [
      { to: '/admin/anomaly-detectors', label: 'Anomaly Detectors', icon: Zap, end: false },
      { to: '/admin/alert-routing', label: 'Alert Routing', icon: Icon.alert, end: false },
      { to: '/admin/maintenance', label: 'Maintenance', icon: Wrench, end: false },
    ],
  },
  {
    group: 'System',
    items: [
      { to: '/admin/models', label: 'Models', icon: Cpu, end: false },
      { to: '/admin/users', label: 'Users', icon: UserCog, end: false },
      { to: '/admin/audit', label: 'Audit Log', icon: Icon.audit, end: false },
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
  const { pathname } = useLocation()
  const [profileOpen, setProfileOpen] = useState(false)

  return (
    <div data-theme="light" className="contents">
      <Helmet title={`${pageTitle} — Admin`} />
      <SidebarProvider>
        <Sidebar collapsible="icon">
          {/* Brand header */}
          <SidebarHeader className="border-b border-sidebar-border px-2 py-3">
            <div className="flex items-center gap-3 px-1">
              <VmsLogo />
              <span className="font-display text-[15px] font-bold tracking-tight text-text-primary group-data-[collapsible=icon]:hidden">
                VMS
              </span>
              <span className="ml-auto shrink-0 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest bg-surface-sunken text-text-muted select-none group-data-[collapsible=icon]:hidden">
                Admin
              </span>
            </div>
          </SidebarHeader>

          {/* Navigation */}
          <SidebarContent>
            <nav aria-label="Admin navigation">
            {NAV_SECTIONS.map((section) => (
              <SidebarGroup key={section.group}>
                <SidebarGroupLabel className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
                  {section.group}
                </SidebarGroupLabel>
                <SidebarMenu>
                  {section.items.map(({ to, label, icon: ItemIcon, end }) => (
                    <SidebarMenuItem key={to}>
                      <NavLink to={to} end={end} className="w-full">
                        {({ isActive }) => (
                          <SidebarMenuButton
                            isActive={isActive}
                            tooltip={label}
                            className={
                              isActive
                                ? 'relative font-medium text-text-primary [border-left:3px_solid_var(--brand-accent)]'
                                : 'text-text-secondary'
                            }
                          >
                            {isActive && (
                              <motion.span
                                layoutId="admin-nav-active"
                                className="absolute inset-0 rounded-md bg-surface-sunken"
                                transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                              />
                            )}
                            <ItemIcon className="relative h-[15px] w-[15px] shrink-0" aria-hidden="true" />
                            <span className="relative">{label}</span>
                          </SidebarMenuButton>
                        )}
                      </NavLink>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarGroup>
            ))}
            </nav>
          </SidebarContent>

          {/* Sidebar footer */}
          <SidebarFooter className="border-t border-sidebar-border">
            <SidebarMenu>
              <SidebarMenuItem>
                <Link to="/live" className="w-full">
                  <SidebarMenuButton tooltip="Live View" className="text-text-secondary">
                    <ExternalLink className="h-[15px] w-[15px] shrink-0" aria-hidden="true" />
                    <span>Live View</span>
                  </SidebarMenuButton>
                </Link>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  tooltip="Sign out"
                  className="text-text-secondary"
                  onClick={() => {
                    logout()
                    navigate('/login', { replace: true })
                  }}
                >
                  <LogOut className="h-[15px] w-[15px] shrink-0" aria-hidden="true" />
                  <span>Sign out</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarFooter>
        </Sidebar>

        {/* ── Main area ─────────────────────────────────────────────────────── */}
        <SidebarInset className="bg-surface-sunken">
          {/* Top bar */}
          <header className="flex h-14 flex-shrink-0 items-center border-b border-border bg-surface-base px-6">
            <span className="text-[15px] font-semibold text-text-primary" aria-hidden="true">
              {pageTitle}
            </span>
            <div className="flex-1" />
            {user && (
              <motion.button
                type="button"
                onClick={() => setProfileOpen(true)}
                aria-label="Open profile settings"
                aria-expanded={profileOpen}
                whileHover={{ scale: 1.06 }}
                whileTap={{ scale: 0.94 }}
                transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[12px] font-bold text-text-inverse select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)] focus-visible:ring-offset-1"
                style={{ background: 'var(--brand-accent)' }}
              >
                {user.userId.slice(0, 2).toUpperCase()}
              </motion.button>
            )}
          </header>

          <ProfileDialog
            open={profileOpen}
            onClose={() => setProfileOpen(false)}
            workspaceId="administration"
          />

          <div className="min-w-0 flex-1 overflow-auto">
            <AnimatePresence mode="wait">
              <motion.div
                key={pathname}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15, ease: [0.4, 0, 0.2, 1] }}
              >
                <Outlet />
              </motion.div>
            </AnimatePresence>
          </div>
        </SidebarInset>
      </SidebarProvider>
    </div>
  )
}
