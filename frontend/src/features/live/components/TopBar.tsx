import { Link, useNavigate } from 'react-router-dom'
import { Icon } from '@/shared/design-system/icons'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/stores/authStore'
import { useCommandPaletteStore } from '@/stores/commandPaletteStore'
import { useLiveStore } from '../store/liveStore'

function VmsLogo() {
  return (
    <div
      className="animate-logo-glow flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--brand-accent)]/30 bg-[#120504]"
      aria-hidden="true"
    >
      <span className="font-display text-[13px] font-bold text-[var(--brand-accent)]">V</span>
    </div>
  )
}

export function TopBar() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const logout = useAuthStore((s) => s.logout)
  const paletteOpen = useCommandPaletteStore((s) => s.open)
  const setPaletteOpen = useCommandPaletteStore((s) => s.setOpen)

  const alerts = useLiveStore((s) => s.alerts)
  const headCount = useLiveStore((s) => s.headCount)
  const gpuPct = useLiveStore((s) => s.gpuPct)

  const activeAlertCount = alerts.filter((a) => a.state === 'OPEN').length

  return (
    <header className="flex h-14 flex-shrink-0 items-center gap-4 border-b border-[#1e293b] bg-[#111827] px-4">
      {/* Logo + title */}
      <Link
        to="/live"
        className="flex items-center gap-2 rounded-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
        aria-label="VMS — home"
      >
        <VmsLogo />
        <span className="font-display text-[15px] font-bold text-slate-100">Live</span>
      </Link>

      {/* Cmd+K search trigger */}
      <button
        type="button"
        className="flex h-9 w-72 items-center gap-2 rounded-[10px] border border-[#1e293b] bg-[#1a2234] px-3 text-[13px] text-slate-400 hover:border-[#334155] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
        onClick={() => setPaletteOpen(true)}
        aria-label="Search persons"
        aria-expanded={paletteOpen}
      >
        <Icon.search className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
        <span className="flex-1 text-left">Search…</span>
        <kbd className="rounded bg-[#232d42] px-1.5 font-mono text-[11px]">⌘K</kbd>
      </button>

      <div className="flex-1" />

      {/* Head count */}
      <div
        className="flex items-center gap-1.5 text-slate-400"
        aria-label={`${headCount.total} people on site`}
      >
        <Icon.users className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="font-mono text-[13px]">{headCount.total}</span>
      </div>

      {/* GPU utilisation bar */}
      <div
        className="flex items-center gap-2"
        role="progressbar"
        aria-valuenow={gpuPct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`GPU ${gpuPct}%`}
      >
        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-[#232d42]">
          <div
            className="h-full rounded-full bg-action-600"
            style={{ width: `${gpuPct}%` }}
          />
        </div>
        <span className="font-mono text-[11px] text-slate-400">{gpuPct}%</span>
      </div>

      {/* Active alerts badge */}
      {activeAlertCount > 0 && (
        <span
          className="flex items-center gap-1 rounded-full bg-[#dc2626] px-2.5 py-1 text-[13px] font-semibold text-white"
          aria-label={`${activeAlertCount} active alerts`}
        >
          <Icon.alert className="h-3.5 w-3.5" aria-hidden="true" />
          {activeAlertCount}
        </span>
      )}

      {/* Admin link */}
      {(user?.role === 'admin' || user?.role === 'manager') && (
        <Link
          to="/admin"
          className="rounded-[10px] px-3 py-1.5 text-[13px] text-slate-400 hover:bg-[#1a2234] hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
        >
          Admin
        </Link>
      )}

      {/* Sign out */}
      <button
        type="button"
        onClick={() => {
          logout()
          navigate('/login', { replace: true })
        }}
        className="rounded-[10px] px-3 py-1.5 text-[13px] text-slate-400 hover:bg-[#1a2234] hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
        aria-label="Sign out"
      >
        {user?.role && <span className="mr-1.5 text-slate-500">{user.role}</span>}
        Sign out
      </button>
    </header>
  )
}
