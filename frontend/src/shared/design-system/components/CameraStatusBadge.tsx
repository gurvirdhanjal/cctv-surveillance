import {
  Radio, Play, CheckCircle2, Cpu, Calendar, Moon,
  RefreshCw, ShieldX, WifiOff, XCircle, Activity, MinusCircle,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/shared/utils/cn'

export type CameraStatus =
  | 'recording' | 'streaming' | 'connected' | 'analytics'
  | 'maintenance' | 'standby' | 'reconnecting' | 'unauthorized'
  | 'unreachable' | 'offline' | 'recovering' | 'disabled'

interface StatusConfig {
  label: string
  colorClass: string
  Icon: LucideIcon
  pulse: boolean
}

const STATUS_CONFIG: Record<CameraStatus, StatusConfig> = {
  recording:    { label: 'Recording',    colorClass: 'text-green-600',  Icon: Radio,        pulse: true  },
  streaming:    { label: 'Streaming',    colorClass: 'text-green-500',  Icon: Play,         pulse: true  },
  connected:    { label: 'Connected',    colorClass: 'text-green-400',  Icon: CheckCircle2, pulse: false },
  analytics:    { label: 'Analytics',    colorClass: 'text-blue-500',   Icon: Cpu,          pulse: false },
  maintenance:  { label: 'Maintenance',  colorClass: 'text-blue-400',   Icon: Calendar,     pulse: false },
  standby:      { label: 'Standby',      colorClass: 'text-gray-400',   Icon: Moon,         pulse: false },
  reconnecting: { label: 'Reconnecting', colorClass: 'text-amber-500',  Icon: RefreshCw,    pulse: true  },
  unauthorized: { label: 'Unauthorized', colorClass: 'text-amber-600',  Icon: ShieldX,      pulse: false },
  unreachable:  { label: 'Unreachable',  colorClass: 'text-gray-500',   Icon: WifiOff,      pulse: false },
  offline:      { label: 'Offline',      colorClass: 'text-gray-500',   Icon: XCircle,      pulse: false },
  recovering:   { label: 'Recovering',   colorClass: 'text-amber-400',  Icon: Activity,     pulse: true  },
  disabled:     { label: 'Disabled',     colorClass: 'text-gray-300',   Icon: MinusCircle,  pulse: false },
}

interface CameraStatusBadgeProps {
  status: CameraStatus
  className?: string
}

export function CameraStatusBadge({ status, className }: CameraStatusBadgeProps) {
  const { label, colorClass, Icon, pulse } = STATUS_CONFIG[status]
  return (
    <span
      role="status"
      aria-label={label}
      className={cn('inline-flex items-center gap-1.5 text-[12px] font-medium', colorClass, className)}
    >
      <span className="relative flex h-1.5 w-1.5">
        {pulse && (
          <span
            className="animate-status-pulse absolute inline-flex h-full w-full rounded-full bg-current opacity-75"
            aria-hidden="true"
          />
        )}
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
      </span>
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {label}
    </span>
  )
}
