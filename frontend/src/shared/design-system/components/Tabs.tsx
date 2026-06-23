import * as RadixTabs from '@radix-ui/react-tabs'
import { cn } from '@/shared/utils/cn'

export const Tabs = RadixTabs.Root
export const TabsList = ({ className, ...props }: RadixTabs.TabsListProps) => (
  <RadixTabs.List
    className={cn(
      'flex gap-1 border-b border-border',
      className,
    )}
    {...props}
  />
)

export const TabsTrigger = ({ className, ...props }: RadixTabs.TabsTriggerProps) => (
  <RadixTabs.Trigger
    className={cn(
      'relative -mb-px px-4 py-2 text-[14px] font-medium text-text-secondary',
      'hover:text-text-primary',
      'focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]',
      'data-[state=active]:text-text-primary',
      'data-[state=active]:after:absolute data-[state=active]:after:inset-x-0',
      'data-[state=active]:after:bottom-0 data-[state=active]:after:h-0.5',
      'data-[state=active]:after:bg-brand-500 data-[state=active]:after:content-[""]',
      className,
    )}
    {...props}
  />
)

export const TabsContent = RadixTabs.Content
