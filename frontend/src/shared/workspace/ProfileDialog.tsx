import { useEffect, useRef } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Sun, Moon, Monitor, LogOut, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useWorkspacePrefs, type WorkspaceTheme, type WorkspaceId } from './useWorkspacePrefs'

const THEME_OPTIONS: { value: WorkspaceTheme; label: string; Icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', Icon: Sun },
  { value: 'dark', label: 'Dark', Icon: Moon },
  { value: 'system', label: 'System', Icon: Monitor },
]

const SPRING = { type: 'spring', stiffness: 400, damping: 30 } as const

interface ProfileDialogProps {
  open: boolean
  onClose: () => void
  workspaceId: WorkspaceId
}

export function ProfileDialog({ open, onClose, workspaceId }: ProfileDialogProps) {
  const navigate = useNavigate()
  const logout = useAuthStore((s) => s.logout)
  const user = useAuthStore((s) => s.user)
  const storedTheme = useWorkspacePrefs((s) => s.workspaceThemes[workspaceId])
  const setWorkspaceTheme = useWorkspacePrefs((s) => s.setWorkspaceTheme)
  const closeRef = useRef<HTMLButtonElement>(null)

  const currentTheme: WorkspaceTheme = storedTheme ?? 'light'
  const activeIndex = THEME_OPTIONS.findIndex((o) => o.value === currentTheme)

  const initials = (user?.userId ?? 'U').slice(0, 2).toUpperCase()

  // Close on Escape
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  // Focus close button on open
  useEffect(() => {
    if (open) closeRef.current?.focus()
  }, [open])

  function handleLogout() {
    onClose()
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-[49] bg-black/20"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={onClose}
            aria-hidden="true"
          />

          {/* Panel */}
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label="Profile settings"
            className="fixed right-5 top-[60px] z-[50] w-[320px] overflow-hidden rounded-xl border border-border bg-surface-base shadow-4"
            initial={{ opacity: 0, y: -10, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.96 }}
            transition={SPRING}
          >
            {/* Close */}
            <button
              ref={closeRef}
              type="button"
              onClick={onClose}
              aria-label="Close profile settings"
              className="absolute right-3 top-3 flex h-6 w-6 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-surface-sunken hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>

            {/* Avatar + identity */}
            <div className="flex items-center gap-3 px-5 pb-4 pt-5">
              <div
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[13px] font-bold text-text-inverse select-none"
                style={{ background: 'var(--brand-accent)' }}
                aria-hidden="true"
              >
                {initials}
              </div>
              <div className="min-w-0">
                <p className="truncate text-[14px] font-semibold text-text-primary">
                  {user?.userId ?? 'Unknown'}
                </p>
                <p className="text-[12px] capitalize text-text-muted">{user?.role ?? '—'}</p>
              </div>
            </div>

            <div className="h-px bg-border" />

            {/* Profile section */}
            <section className="px-5 py-4">
              <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                Profile
              </p>
              <div className="space-y-2.5">
                <Row label="Username" value={user?.userId ?? '—'} />
                <Row label="Role" value={user?.role ?? '—'} capitalize />
              </div>
            </section>

            <div className="h-px bg-border" />

            {/* Preferences / theme */}
            <section className="px-5 py-4">
              <p className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                Appearance
              </p>
              <div className="relative flex rounded-lg bg-surface-sunken p-1">
                {/* Spring-animated pill indicator */}
                <motion.div
                  className="absolute inset-y-1 rounded-md bg-surface-base shadow-1"
                  animate={{
                    left: `calc(${activeIndex} * 33.333% + 4px)`,
                    width: 'calc(33.333% - 8px)',
                  }}
                  transition={SPRING}
                />
                {THEME_OPTIONS.map(({ value, label, Icon }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setWorkspaceTheme(workspaceId, value)}
                    className={[
                      'relative z-10 flex flex-1 items-center justify-center gap-1.5 rounded-md py-1.5',
                      'text-[12px] font-medium transition-colors duration-fast',
                      currentTheme === value
                        ? 'text-text-primary'
                        : 'text-text-muted hover:text-text-secondary',
                    ].join(' ')}
                  >
                    <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                    {label}
                  </button>
                ))}
              </div>
            </section>

            <div className="h-px bg-border" />

            {/* Logout */}
            <div className="px-5 py-4">
              <motion.button
                type="button"
                onClick={handleLogout}
                whileTap={{ scale: 0.98 }}
                className="flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13px] font-medium text-error transition-colors hover:bg-error/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]"
              >
                <LogOut className="h-4 w-4" aria-hidden="true" />
                Sign out
              </motion.button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

function Row({
  label,
  value,
  capitalize,
}: {
  label: string
  value: string
  capitalize?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-[12px] text-text-muted">{label}</span>
      <span
        className={[
          'text-[12px] font-medium text-text-primary',
          capitalize ? 'capitalize' : '',
        ].join(' ')}
      >
        {value}
      </span>
    </div>
  )
}
