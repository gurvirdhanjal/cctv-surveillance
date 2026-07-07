import { forwardRef, type HTMLAttributes } from 'react'
import { cn } from '@/shared/utils/cn'
import { type SpacingToken } from './Stack'

// Reuse the gap map from Stack
const GAP: Record<SpacingToken, string> = {
  2:  'gap-0.5',
  4:  'gap-1',
  8:  'gap-2',
  12: 'gap-3',
  16: 'gap-4',
  20: 'gap-5',
  24: 'gap-6',
  32: 'gap-8',
  40: 'gap-10',
  48: 'gap-12',
  64: 'gap-16',
  80: 'gap-20',
  96: 'gap-24',
}

type AlignValue = 'start' | 'end' | 'center' | 'stretch' | 'baseline'
type JustifyValue = 'start' | 'end' | 'center' | 'between' | 'around' | 'evenly'

const ALIGN: Record<AlignValue, string> = {
  start:    'items-start',
  end:      'items-end',
  center:   'items-center',
  stretch:  'items-stretch',
  baseline: 'items-baseline',
}
const JUSTIFY: Record<JustifyValue, string> = {
  start:   'justify-start',
  end:     'justify-end',
  center:  'justify-center',
  between: 'justify-between',
  around:  'justify-around',
  evenly:  'justify-evenly',
}

export interface ClusterProps extends HTMLAttributes<HTMLDivElement> {
  /** @role Information — horizontal wrapping flex container */
  gap: SpacingToken
  align?: AlignValue
  justify?: JustifyValue
}

export const Cluster = forwardRef<HTMLDivElement, ClusterProps>(function Cluster(
  { gap, align, justify, className, children, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn(
        'flex flex-row flex-wrap',
        GAP[gap],
        align && ALIGN[align],
        justify && JUSTIFY[justify],
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  )
})
