import { cn } from "@/shared/utils/cn"

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-surface-raised", className)}
      {...props}
    />
  )
}

export { Skeleton }
