import * as Dialog from '@radix-ui/react-dialog'
import { Icon } from '@/shared/design-system/icons'

const SHORTCUTS: { key: string; description: string }[] = [
  { key: 'A', description: 'Acknowledge selected alarm' },
  { key: 'R', description: 'Resolve selected alarm' },
  { key: 'B', description: 'Bookmark current frame' },
  { key: 'E', description: 'Export clip' },
  { key: 'N', description: 'Next camera' },
  { key: 'F', description: 'Toggle follow mode' },
  { key: 'Space', description: 'Play / pause (focused video)' },
  { key: '←  →', description: 'Scrub ∓5 seconds' },
  { key: '?', description: 'Toggle this legend' },
  { key: 'Esc', description: 'Close modal / clear selection' },
  { key: '⌘K', description: 'Search (Command palette)' },
]

interface ShortcutLegendProps {
  open: boolean
  onClose: () => void
}

export function ShortcutLegend({ open, onClose }: ShortcutLegendProps) {
  return (
    <Dialog.Root open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-[#1e293b] bg-[#111827] p-6 shadow-3 focus:outline-none"
          aria-label="Keyboard shortcuts"
        >
          <div className="flex items-center justify-between">
            <Dialog.Title className="text-[15px] font-semibold text-slate-100">
              Keyboard Shortcuts
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded-[10px] p-1.5 text-slate-400 hover:bg-[#1a2234] hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
                aria-label="Close"
              >
                <Icon.close className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2.5">
            {SHORTCUTS.map(({ key, description }) => (
              <div key={key} className="flex items-center gap-2">
                <kbd className="flex-shrink-0 rounded bg-[#232d42] px-1.5 py-0.5 font-mono text-[11px] text-slate-200">
                  {key}
                </kbd>
                <span className="text-[13px] text-slate-400">{description}</span>
              </div>
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
