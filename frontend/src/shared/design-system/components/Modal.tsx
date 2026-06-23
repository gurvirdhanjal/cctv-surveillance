import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { cn } from '@/shared/utils/cn'

export interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: React.ReactNode
  /** Extra classes on the panel. */
  className?: string
  /** Prevent closing by clicking the scrim. */
  preventCloseOnOverlay?: boolean
}

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  className,
  preventCloseOnOverlay = false,
}: ModalProps) {
  return (
    <Dialog.Root open={open} onOpenChange={(v) => !v && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-40 bg-[var(--overlay-scrim)] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
          onClick={preventCloseOnOverlay ? (e) => e.stopPropagation() : undefined}
        />
        <Dialog.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2',
            'w-full max-w-[560px] rounded-lg bg-surface-base shadow-3',
            'data-[state=open]:animate-in data-[state=closed]:animate-out',
            'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
            'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
            'focus-visible:outline-none',
            className,
          )}
          aria-describedby={description ? 'modal-description' : undefined}
        >
          {/* Header */}
          <div className="flex items-start justify-between border-b border-border p-6 pb-4">
            <div>
              <Dialog.Title className="text-[20px] font-semibold text-text-primary">
                {title}
              </Dialog.Title>
              {description && (
                <Dialog.Description
                  id="modal-description"
                  className="mt-1 text-[14px] text-text-secondary"
                >
                  {description}
                </Dialog.Description>
              )}
            </div>
            <Dialog.Close asChild>
              <button
                className="ml-4 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md text-text-muted hover:bg-surface-raised hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
                aria-label="Close dialog"
              >
                <X size={16} aria-hidden />
              </button>
            </Dialog.Close>
          </div>
          {/* Body */}
          <div className="p-6">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
