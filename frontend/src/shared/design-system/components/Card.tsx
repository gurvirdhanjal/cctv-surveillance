import { type HTMLAttributes } from 'react'
import { cn } from '@/shared/utils/cn'

/** §A canonical Card variant set — complete closed set. */
type CardVariant = 'metric' | 'health' | 'camera' | 'alarm' | 'timeline' | 'configuration'

const VARIANT_CLASSES: Record<CardVariant, string> = {
  metric:        'p-4',
  health:        'p-4',
  camera:        'p-3',
  alarm:         'p-4 border border-[var(--destructive)]/20',
  timeline:      'p-3',
  configuration: 'p-5',
}

interface CardRootProps extends HTMLAttributes<HTMLDivElement> {
  /** @role Information — content surface; variant sets padding + accent treatment */
  variant: CardVariant
}

function CardRoot({ variant, className, children, ...rest }: CardRootProps) {
  return (
    <div
      className={cn(
        'rounded-xl bg-surface-raised shadow-2',
        VARIANT_CLASSES[variant],
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  )
}

function CardHeader({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('mb-2 flex items-center justify-between', className)} {...rest}>
      {children}
    </div>
  )
}

function CardBody({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('flex-1', className)} {...rest}>
      {children}
    </div>
  )
}

function CardFooter({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('mt-3 flex items-center gap-2', className)} {...rest}>
      {children}
    </div>
  )
}

function CardActions({ className, children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('mt-2 flex items-center gap-2', className)} {...rest}>
      {children}
    </div>
  )
}

export const Card = {
  Root:    CardRoot,
  Header:  CardHeader,
  Body:    CardBody,
  Footer:  CardFooter,
  Actions: CardActions,
}
