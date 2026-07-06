import type { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: string
  action?: React.ReactNode
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface-base py-20 text-center">
      <Icon className="mb-4 h-10 w-10 text-text-muted opacity-30" aria-hidden="true" />
      <p className="text-[15px] font-semibold text-text-secondary">{title}</p>
      {description && <p className="mt-1 text-[13px] text-text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
