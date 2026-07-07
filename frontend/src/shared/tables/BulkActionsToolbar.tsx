import { motion, useReducedMotion } from 'framer-motion'
import { MOTION } from '@/shared/motion/motion'
import type { ReactNode } from 'react'

export interface BulkAction {
  label: string
  icon: ReactNode
  onClick: () => void
  variant?: 'default' | 'danger'
}

interface BulkActionsToolbarProps {
  selectedCount: number
  actions: BulkAction[]
}

export function BulkActionsToolbar({ selectedCount, actions }: BulkActionsToolbarProps) {
  const reduced = useReducedMotion()

  return (
    <motion.div
      data-bulk-toolbar
      role="toolbar"
      aria-label="Bulk actions"
      initial={reduced ? false : { y: 8, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={reduced ? undefined : { y: 8, opacity: 0 }}
      transition={MOTION.dropdown}
      className="flex items-center gap-3 rounded-xl border border-border bg-surface-raised px-4 py-2 shadow-2"
    >
      <span className="text-sm font-medium text-text-primary">
        {selectedCount} selected
      </span>
      <div className="h-4 w-px bg-border" />
      {actions.map((action) => (
        <button
          key={action.label}
          type="button"
          onClick={action.onClick}
          className={
            action.variant === 'danger'
              ? 'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-[var(--alarm-red)] hover:bg-surface-sunken transition-colors'
              : 'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-text-primary hover:bg-surface-sunken transition-colors'
          }
        >
          {action.icon}
          {action.label}
        </button>
      ))}
    </motion.div>
  )
}
