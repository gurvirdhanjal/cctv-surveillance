import type { ReactNode, HTMLAttributes } from 'react'
import { cn } from '@/shared/utils/cn'
import { Cluster } from '../primitives/Cluster'

interface ActionBarProps extends HTMLAttributes<HTMLDivElement> {
  /** Left slot — title, breadcrumb, or contextual label. */
  left?: ReactNode
  /** Right slot — action buttons grouped in a Cluster. */
  right?: ReactNode
  /** Pin the bar to the top of its scroll container. */
  sticky?: boolean
  /** Apply glass-toolbar backdrop blur (§M). */
  glass?: boolean
}

/** §S Unified Action Bar — left/right slots, toolbar elevation, optional sticky + glass. */
export function ActionBar({
  left,
  right,
  sticky = false,
  glass = false,
  className,
  children,
  ...rest
}: ActionBarProps) {
  return (
    <div
      role="toolbar"
      className={cn(
        'flex items-center justify-between px-4 py-2 bg-surface-raised border-b border-border',
        'z-toolbar shadow-2',
        sticky && 'sticky top-0',
        glass && 'glass-toolbar',
        className,
      )}
      {...rest}
    >
      {left && <div className="flex items-center min-w-0">{left}</div>}
      {right && (
        <Cluster gap={8} align="center" className="ml-auto">
          {right}
        </Cluster>
      )}
      {children}
    </div>
  )
}
