const STATE_META = {
  online: { dot: 'animate-status-pulse bg-white', bg: 'bg-success/85', label: 'Online' },
  offline: { dot: 'bg-white/40', bg: 'bg-black/55', label: 'Offline' },
  maintenance: { dot: 'bg-white/80', bg: 'bg-info/85', label: 'Maintenance' },
  auth_failed: { dot: 'bg-white/80', bg: 'bg-warning/85', label: 'Auth Failed' },
  critical: { dot: 'animate-status-pulse bg-white', bg: 'bg-error/85', label: 'Critical' },
} as const

type StatusState = keyof typeof STATE_META

interface StatusBadge5Props {
  state: StatusState
}

export function StatusBadge5({ state }: StatusBadge5Props) {
  const m = STATE_META[state]
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full ${m.bg} px-2 py-0.5 text-[11px] font-semibold text-white backdrop-blur-sm`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${m.dot}`} />
      {m.label}
    </span>
  )
}
