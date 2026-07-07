import * as React from 'react'
import * as SwitchPrimitive from '@radix-ui/react-switch'
import { motion } from 'framer-motion'
import { cn } from '@/shared/utils/cn'

/** §O exact spring config for switch thumb animation. */
export const TOGGLE_SPRING = { type: 'spring', stiffness: 400, damping: 25 } as const

const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>
>(({ className, checked: checkedProp, defaultChecked, onCheckedChange, ...props }, ref) => {
  const isControlled = checkedProp !== undefined
  const [internalChecked, setInternalChecked] = React.useState(
    isControlled ? checkedProp : (defaultChecked ?? false)
  )
  const isChecked = isControlled ? checkedProp : internalChecked

  const handleCheckedChange = (val: boolean) => {
    if (!isControlled) setInternalChecked(val)
    onCheckedChange?.(val)
  }

  return (
    <SwitchPrimitive.Root
      ref={ref}
      checked={isChecked}
      onCheckedChange={handleCheckedChange}
      className={cn(
        'peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-surface-base',
        'disabled:cursor-not-allowed disabled:opacity-50',
        'data-[state=unchecked]:bg-border-strong data-[state=checked]:bg-interactive-primary',
        className
      )}
      {...props}
    >
      <motion.span
        aria-hidden="true"
        className="pointer-events-none block h-4 w-4 rounded-full bg-white shadow-1 ring-0"
        animate={{ x: isChecked ? 16 : 0 }}
        transition={TOGGLE_SPRING}
      />
    </SwitchPrimitive.Root>
  )
})
Switch.displayName = SwitchPrimitive.Root.displayName

export { Switch }
