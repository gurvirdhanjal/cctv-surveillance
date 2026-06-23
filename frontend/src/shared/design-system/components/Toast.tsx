import * as RadixToast from '@radix-ui/react-toast'
import { X, CheckCircle2, AlertCircle, Info, AlertTriangle } from 'lucide-react'
import { cn } from '@/shared/utils/cn'

export type ToastSeverity = 'success' | 'error' | 'warning' | 'info'

export interface ToastItem {
  id: string
  severity: ToastSeverity
  title: string
  description?: string
}

const icons: Record<ToastSeverity, React.ReactNode> = {
  success: <CheckCircle2 size={16} aria-hidden />,
  error: <AlertCircle size={16} aria-hidden />,
  warning: <AlertTriangle size={16} aria-hidden />,
  info: <Info size={16} aria-hidden />,
}

const colorClass: Record<ToastSeverity, string> = {
  success: 'text-[var(--success)]',
  error: 'text-[var(--error)]',
  warning: 'text-[var(--warning)]',
  info: 'text-[var(--info)]',
}

interface ToastProps {
  toast: ToastItem
  onDismiss: (id: string) => void
}

export function Toast({ toast, onDismiss }: ToastProps) {
  const isError = toast.severity === 'error'
  return (
    <RadixToast.Root
      open
      onOpenChange={(v) => !v && onDismiss(toast.id)}
      aria-live={isError ? 'assertive' : 'polite'}
      aria-atomic="true"
      className={cn(
        'flex items-start gap-3 rounded-lg border border-border bg-surface-base p-4 shadow-3',
        'data-[state=open]:animate-in data-[state=closed]:animate-out',
        'data-[state=closed]:slide-out-to-right-full data-[state=open]:slide-in-from-right-full',
        'data-[state=closed]:fade-out-80',
      )}
    >
      <span className={cn('mt-0.5 flex-shrink-0', colorClass[toast.severity])}>
        {icons[toast.severity]}
      </span>
      <div className="flex-1">
        <RadixToast.Title className="text-[14px] font-medium text-text-primary">
          {toast.title}
        </RadixToast.Title>
        {toast.description && (
          <RadixToast.Description className="mt-0.5 text-[13px] text-text-secondary">
            {toast.description}
          </RadixToast.Description>
        )}
      </div>
      <RadixToast.Close asChild>
        <button
          className="flex-shrink-0 rounded text-text-muted hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
          aria-label="Dismiss notification"
        >
          <X size={14} aria-hidden />
        </button>
      </RadixToast.Close>
    </RadixToast.Root>
  )
}

export interface ToastProviderProps {
  toasts: ToastItem[]
  onDismiss: (id: string) => void
}

export function ToastProvider({ toasts, onDismiss }: ToastProviderProps) {
  return (
    <RadixToast.Provider swipeDirection="right">
      {toasts.map((t) => (
        <Toast key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
      <RadixToast.Viewport className="fixed bottom-4 right-4 z-[100] flex w-[380px] max-w-[100vw] flex-col gap-2" />
    </RadixToast.Provider>
  )
}
