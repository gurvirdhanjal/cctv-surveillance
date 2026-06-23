import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/shared/utils/cn'
import { Spinner } from './Spinner'

const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-2 rounded-md font-medium',
    'transition-colors duration-[120ms]',
    'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2',
    'focus-visible:outline-[var(--focus-ring)]',
    'aria-disabled:pointer-events-none aria-disabled:bg-[var(--disabled-bg)]',
    'aria-disabled:text-[var(--disabled-text)] aria-disabled:border-[var(--disabled-bg)]',
    'select-none',
  ],
  {
    variants: {
      variant: {
        primary: [
          'bg-brand-500 text-text-inverse shadow-1',
          'hover:bg-[var(--interactive-hover)]',
          'active:bg-[var(--interactive-active)]',
        ],
        secondary: [
          'border border-border bg-transparent text-text-primary',
          'hover:bg-surface-raised',
          'active:bg-surface-sunken',
        ],
        ghost: [
          'bg-transparent text-text-primary',
          'hover:bg-surface-raised',
          'active:bg-surface-sunken',
        ],
        destructive: [
          'bg-[var(--destructive)] text-white shadow-1',
          'hover:bg-[var(--destructive-hover)]',
        ],
      },
      size: {
        sm: 'h-8 px-3 text-[13px]',
        md: 'h-10 px-4 text-[14px]',
        lg: 'h-12 px-5 text-[16px]',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  },
)

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean
  /** Icon rendered before the label. */
  icon?: React.ReactNode
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading = false, disabled, icon, children, ...props }, ref) => {
    const isDisabled = disabled || loading
    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={isDisabled}
        aria-disabled={isDisabled || undefined}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading ? (
          <Spinner size={size === 'sm' ? 14 : size === 'lg' ? 18 : 16} aria-hidden />
        ) : (
          icon
        )}
        {children}
      </button>
    )
  },
)

Button.displayName = 'Button'
