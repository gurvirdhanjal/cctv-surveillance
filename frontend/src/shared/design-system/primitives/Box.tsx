import { forwardRef, type ElementType, type ComponentPropsWithRef } from 'react'
import { cn } from '@/shared/utils/cn'

type BoxProps<T extends ElementType = 'div'> = {
  /** @role Information — neutral layout container */
  as?: T
  className?: string
  children?: React.ReactNode
} & Omit<ComponentPropsWithRef<T>, 'as'>

export const Box = forwardRef(function Box<T extends ElementType = 'div'>(
  { as, className, children, ...rest }: BoxProps<T>,
  ref: React.Ref<Element>,
) {
  const Tag = (as ?? 'div') as ElementType
  return (
    <Tag ref={ref} className={cn(className)} {...rest}>
      {children}
    </Tag>
  )
}) as <T extends ElementType = 'div'>(props: BoxProps<T> & { ref?: React.Ref<Element> }) => React.ReactElement | null
