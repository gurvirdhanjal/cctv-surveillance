import { Lock, Upload } from 'lucide-react'
import { Icon } from '../icons'
import { cn } from '@/shared/utils/cn'

/** §K closed set — 13 camera/system states. */
export type CameraStatus =
  | 'online' | 'recording' | 'streaming' | 'analytics' | 'maintenance'
  | 'updating' | 'initializing' | 'disconnected' | 'unauthorized'
  | 'syncing' | 'calibrating' | 'training' | 'importing'

interface StatusConfig {
  label: string
  colorClass: string
  IconComponent: React.ElementType
  pulse: boolean
  spin: boolean
}

const STATUS_CONFIG: Record<CameraStatus, StatusConfig> = {
  online:       { label: 'Online',       colorClass: 'text-green-600',   IconComponent: Icon.camera,      pulse: false, spin: false },
  recording:    { label: 'Recording',    colorClass: 'text-red-600',     IconComponent: Icon.recording,   pulse: true,  spin: false },
  streaming:    { label: 'Streaming',    colorClass: 'text-blue-500',    IconComponent: Icon.live,         pulse: false, spin: false },
  analytics:    { label: 'Analytics',    colorClass: 'text-purple-500',  IconComponent: Icon.analytics,   pulse: false, spin: false },
  maintenance:  { label: 'Maintenance',  colorClass: 'text-amber-500',   IconComponent: Icon.calendar,    pulse: false, spin: false },
  updating:     { label: 'Updating',     colorClass: 'text-blue-500',    IconComponent: Icon.sync,        pulse: false, spin: true  },
  initializing: { label: 'Initializing', colorClass: 'text-gray-400',    IconComponent: Icon.sync,        pulse: true,  spin: false },
  disconnected: { label: 'Disconnected', colorClass: 'text-red-400',     IconComponent: Icon.disconnected,pulse: false, spin: false },
  unauthorized: { label: 'Unauthorized', colorClass: 'text-orange-500',  IconComponent: Lock,             pulse: false, spin: false },
  syncing:      { label: 'Syncing',      colorClass: 'text-blue-400',    IconComponent: Icon.sync,        pulse: false, spin: true  },
  calibrating:  { label: 'Calibrating',  colorClass: 'text-teal-500',    IconComponent: Icon.calibrate,   pulse: false, spin: false },
  training:     { label: 'Training',     colorClass: 'text-violet-500',  IconComponent: Icon.ai,          pulse: true,  spin: false },
  importing:    { label: 'Importing',    colorClass: 'text-blue-500',    IconComponent: Upload,           pulse: false, spin: false },
}

interface CameraStatusBadgeProps {
  status: CameraStatus
  className?: string
}

export function CameraStatusBadge({ status, className }: CameraStatusBadgeProps) {
  const { label, colorClass, IconComponent, pulse, spin } = STATUS_CONFIG[status]
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
      <IconComponent
        className={cn('h-3.5 w-3.5', spin && 'animate-spin')}
        aria-hidden="true"
      />
      {label}
    </span>
  )
}
