import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/shared/utils/cn'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.06em]',
  {
    variants: {
      variant: {
        /** Severity badges */
        critical: 'bg-[var(--severity-critical)] text-white',
        high: 'bg-[var(--severity-high)] text-white',
        medium: 'bg-[var(--severity-medium)] text-white',
        low: 'bg-[var(--severity-low)] text-white',
        /** Camera capability tier */
        full: 'bg-brand-500 text-white',
        mid: 'bg-brand-300 text-brand-900',
        tier_low: 'bg-surface-sunken text-text-secondary border border-border',
        /** Generic */
        default: 'bg-surface-sunken text-text-secondary',
        success: 'bg-[var(--success)] text-white',
        info: 'bg-[var(--info)] text-white',
        warning: 'bg-[var(--warning)] text-white',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  icon?: React.ReactNode
}

export function Badge({ className, variant, icon, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props}>
      {icon}
      {children}
    </span>
  )
}
