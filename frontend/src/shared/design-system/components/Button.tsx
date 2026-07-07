import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/shared/utils/cn'
import { Spinner } from './Spinner'

/** §A canonical Button variant set — no other variants may be added without spec approval. */
const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-2 rounded-md font-medium',
    'transition-colors duration-quick',
    'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2',
    'focus-visible:outline-[var(--focus-ring)]',
    'aria-disabled:pointer-events-none aria-disabled:bg-[var(--disabled-bg)]',
    'aria-disabled:text-[var(--disabled-text)] aria-disabled:border-[var(--disabled-bg)]',
    'select-none',
  ],
  {
    variants: {
      variant: {
        /** @role Action — charcoal primary CTA */
        primary: [
          'bg-action-700 text-text-inverse shadow-1',
          'hover:bg-action-800',
          'active:bg-action-900',
        ],
        /** @role Action — outlined secondary */
        secondary: [
          'border border-border bg-transparent text-text-primary',
          'hover:bg-surface-raised',
          'active:bg-surface-sunken',
        ],
        /** @role Action — ghost, no border */
        ghost: [
          'bg-transparent text-text-primary',
          'hover:bg-surface-raised',
          'active:bg-surface-sunken',
        ],
        /** @role Danger — alarm-red destructive action */
        destructive: [
          'bg-[var(--destructive)] text-white shadow-1',
          'hover:bg-[var(--destructive-hover)]',
        ],
        /** @role Action — square icon button, 32px, no shadow, for toolbars */
        icon: [
          'w-8 p-0 rounded-sm',
          'bg-transparent text-text-primary',
          'hover:bg-surface-raised',
          'active:bg-surface-sunken',
        ],
        /** @role Action — 32px height, radius-sm, no shadow, for floating action bars */
        toolbar: [
          'px-3 text-[13px] rounded-sm',
          'bg-transparent text-text-primary',
          'hover:bg-surface-raised',
          'active:bg-surface-sunken',
        ],
        /** @role Action — primary action + split dropdown chevron */
        split: [
          'bg-action-700 text-text-inverse shadow-1 rounded-md',
          'hover:bg-action-800',
          'active:bg-action-900',
        ],
      },
      size: {
        sm: 'h-8 px-3 text-[13px]',
        md: 'h-10 px-4 text-[14px]',
        lg: 'h-12 px-5 text-[16px]',
      },
    },
    compoundVariants: [
      // icon and toolbar are always 32px regardless of size prop
      { variant: 'icon',    class: 'h-8' },
      { variant: 'toolbar', class: 'h-8' },
    ],
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  },
)

export interface SplitMenuItem {
  label: string
  onClick: () => void
  disabled?: boolean
}

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean
  /** Icon rendered before the label. */
  icon?: React.ReactNode
  /** Split variant: called when the primary action part is clicked. */
  onPrimary?: () => void
  /** Split variant: overflow menu items. */
  menuItems?: SplitMenuItem[]
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className, variant, size, loading = false, disabled,
      icon, children, onPrimary, menuItems: _menuItems, onClick, ...props
    },
    ref,
  ) => {
    const isDisabled = disabled || loading
    const handleClick = variant === 'split' && onPrimary
      ? (e: React.MouseEvent<HTMLButtonElement>) => { onPrimary(); onClick?.(e) }
      : onClick
    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={isDisabled}
        aria-disabled={isDisabled || undefined}
        aria-busy={loading || undefined}
        onClick={handleClick}
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
