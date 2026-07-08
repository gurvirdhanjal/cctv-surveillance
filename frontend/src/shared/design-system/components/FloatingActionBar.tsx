import { motion, useReducedMotion } from 'framer-motion'
import type { LucideIcon } from 'lucide-react'

export interface FloatingAction {
  icon: LucideIcon
  label: string
  onClick: () => void
  disabled?: boolean
}

interface FloatingActionBarProps {
  actions: FloatingAction[]
  className?: string
}

const MOTION_VARIANTS = {
  initial: { y: 8, opacity: 0 },
  animate: { y: 0, opacity: 1 },
}

export function FloatingActionBar({ actions, className }: FloatingActionBarProps) {
  const prefersReduced = useReducedMotion()

  const shown = actions.slice(0, 5)

  return (
    <motion.div
      role="toolbar"
      aria-label="Camera actions"
      className={`absolute bottom-0 left-0 right-0 z-40 flex items-center justify-center gap-1 bg-black/70 px-2 py-1.5 backdrop-blur-sm ${className ?? ''}`}
      initial={prefersReduced ? { y: 0, opacity: 1 } : MOTION_VARIANTS.initial}
      animate={MOTION_VARIANTS.animate}
      transition={{ duration: 0.12, ease: [0.4, 0, 0.2, 1] }}
    >
      {shown.map((action) => {
        const IconComp = action.icon
        return (
          <button
            key={action.label}
            type="button"
            aria-label={action.label}
            disabled={action.disabled}
            onClick={action.onClick}
            className="inline-flex h-7 items-center gap-1 rounded-lg px-2 text-[11px] font-medium text-white/80 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            <IconComp className="h-3.5 w-3.5" aria-hidden="true" />
            {action.label}
          </button>
        )
      })}
    </motion.div>
  )
}
