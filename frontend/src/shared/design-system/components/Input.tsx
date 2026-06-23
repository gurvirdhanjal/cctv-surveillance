import { forwardRef, useId, type InputHTMLAttributes } from 'react'
import { cn } from '@/shared/utils/cn'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  error?: string
  hint?: string
  /** Hide the label visually while keeping it accessible. */
  labelHidden?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, labelHidden, className, id: idProp, ...props }, ref) => {
    const generatedId = useId()
    const id = idProp ?? generatedId
    const errorId = `${id}-error`
    const hintId = `${id}-hint`
    const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ')

    return (
      <div className="flex flex-col gap-1">
        <label
          htmlFor={id}
          className={cn(
            'text-[13px] font-medium text-text-secondary',
            labelHidden && 'sr-only',
          )}
        >
          {label}
        </label>
        <input
          ref={ref}
          id={id}
          aria-invalid={!!error || undefined}
          aria-describedby={describedBy || undefined}
          className={cn(
            'h-10 w-full rounded-md border border-border bg-surface-base px-3',
            'text-[14px] text-text-primary placeholder:text-text-muted',
            'transition-colors duration-[120ms]',
            'hover:border-border-strong',
            'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2',
            'focus-visible:outline-[var(--focus-ring)]',
            'disabled:cursor-not-allowed disabled:bg-[var(--disabled-bg)]',
            'disabled:text-[var(--disabled-text)]',
            error && 'border-[var(--error)] focus-visible:outline-[var(--error)]',
            className,
          )}
          {...props}
        />
        {hint && !error && (
          <p id={hintId} className="text-[12px] text-text-muted">
            {hint}
          </p>
        )}
        {error && (
          <p id={errorId} role="alert" className="text-[12px] text-[var(--error)]">
            {error}
          </p>
        )}
      </div>
    )
  },
)

Input.displayName = 'Input'
