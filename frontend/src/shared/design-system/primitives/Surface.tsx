import { forwardRef, type ElementType, type ComponentPropsWithRef } from 'react'
import { cn } from '@/shared/utils/cn'
import { type ElevationLayer } from '../elevation'

/** Maps elevation layer name → Tailwind shadow + bg token classes. */
const ELEVATION_CLASSES: Record<ElevationLayer, string> = {
  bg:       'bg-surface-sunken',
  surface:  'bg-surface-base shadow-1',
  raised:   'bg-surface-raised shadow-2',
  selected: 'bg-surface-raised shadow-2',
  toolbar:  'bg-surface-raised shadow-2 z-toolbar',
  modal:    'bg-surface-raised shadow-3 z-modal',
  cmdk:     'bg-surface-raised shadow-3 z-cmdk',
  toast:    'bg-surface-raised shadow-4 z-toast',
}

type SurfaceProps<T extends ElementType = 'div'> = {
  /** @role Overlay — elevated surface container */
  elevation: ElevationLayer
  as?: T
  className?: string
  children?: React.ReactNode
} & Omit<ComponentPropsWithRef<T>, 'as' | 'elevation'>

export const Surface = forwardRef(function Surface<T extends ElementType = 'div'>(
  { elevation, as, className, children, ...rest }: SurfaceProps<T>,
  ref: React.Ref<Element>,
) {
  const Tag = (as ?? 'div') as ElementType
  return (
    <Tag
      ref={ref}
      className={cn('rounded-lg', ELEVATION_CLASSES[elevation], className)}
      {...rest}
    >
      {children}
    </Tag>
  )
}) as <T extends ElementType = 'div'>(
  props: SurfaceProps<T> & { ref?: React.Ref<Element> },
) => React.ReactElement | null
