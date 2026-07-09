'use client'

import { motion, useReducedMotion, type Variants } from 'framer-motion'
import { cn } from '@/shared/utils/cn'

const dotSizes = {
  sm: 'h-1.5 w-1.5',
  md: 'h-2 w-2',
  lg: 'h-2.5 w-2.5',
} as const

interface Props {
  className?: string
  size?: keyof typeof dotSizes
}

export function LoadingThreeDotsJumping({ className, size = 'md' }: Props) {
  const shouldReduce = useReducedMotion()

  const dotVariants: Variants = {
    jump: {
      y: -8,
      transition: {
        duration: 0.4,
        repeat: Infinity,
        repeatType: 'mirror',
        ease: 'easeInOut',
      },
    },
  }

  return (
    <motion.div
      role="status"
      aria-label="Loading"
      animate={shouldReduce ? undefined : 'jump'}
      transition={shouldReduce ? undefined : { staggerChildren: 0.12, staggerDirection: -1 }}
      className={cn('flex items-center justify-center gap-1.5', className)}
    >
      <motion.span
        className={cn('rounded-full bg-[var(--brand-accent)]', dotSizes[size])}
        variants={dotVariants}
      />
      <motion.span
        className={cn('rounded-full bg-[var(--brand-accent)]', dotSizes[size])}
        variants={dotVariants}
      />
      <motion.span
        className={cn('rounded-full bg-[var(--brand-accent)]', dotSizes[size])}
        variants={dotVariants}
      />
    </motion.div>
  )
}
