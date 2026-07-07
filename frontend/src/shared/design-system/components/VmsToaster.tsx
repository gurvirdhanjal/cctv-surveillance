import { Toaster, toast } from 'sonner'
import { Icon } from '../icons'

/** §V.1 VMS toast wrapper — maps severity to semantic icon + uses sonner. */
export const vmsToast = {
  success: (message: string, opts?: Parameters<typeof toast.success>[1]) =>
    toast.success(message, {
      icon: <Icon.alert className="h-4 w-4 text-[var(--success)]" aria-hidden />,
      ...opts,
    }),

  error: (message: string, opts?: Parameters<typeof toast.error>[1]) =>
    toast.error(message, {
      icon: <Icon.alert className="h-4 w-4 text-[var(--error)]" aria-hidden />,
      important: true,
      ...opts,
    }),

  warning: (message: string, opts?: Parameters<typeof toast.warning>[1]) =>
    toast.warning(message, {
      icon: <Icon.alert className="h-4 w-4 text-[var(--warning)]" aria-hidden />,
      ...opts,
    }),

  info: (message: string, opts?: Parameters<typeof toast.info>[1]) =>
    toast.info(message, {
      icon: <Icon.alert className="h-4 w-4 text-[var(--info)]" aria-hidden />,
      ...opts,
    }),
} as const

/** §V.1 Mount once at the app root. Binds Sonner's Toaster with VMS config. */
export function VmsToaster() {
  return (
    <Toaster
      position="bottom-right"
      theme="system"
      richColors={false}
      closeButton
      className="z-toast"
      containerAriaLabel="Notifications"
      toastOptions={{
        duration: 5000,
        classNames: {
          toast: 'rounded-xl border border-border bg-surface-base shadow-4',
          title: 'text-[14px] font-medium text-text-primary',
          description: 'text-[13px] text-text-secondary',
          closeButton: 'text-text-muted hover:text-text-primary',
        },
      }}
    />
  )
}
