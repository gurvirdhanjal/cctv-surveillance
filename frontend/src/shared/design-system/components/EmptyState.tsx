import type { LucideIcon } from 'lucide-react'
import { cn } from '@/shared/utils/cn'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
}

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface-base py-20 text-center',
        className,
      )}
    >
      <Icon className="mb-4 h-10 w-10 text-text-muted opacity-30" aria-hidden="true" />
      <p className="text-[15px] font-semibold text-text-secondary">{title}</p>
      {description && <p className="mt-1 text-[13px] text-text-muted">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
