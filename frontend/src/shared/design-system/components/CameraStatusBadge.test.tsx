import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CameraStatusBadge, type CameraStatus } from './CameraStatusBadge'

const ALL_STATES: { status: CameraStatus; label: string }[] = [
  { status: 'recording',    label: 'Recording'    },
  { status: 'streaming',    label: 'Streaming'    },
  { status: 'connected',    label: 'Connected'    },
  { status: 'analytics',    label: 'Analytics'    },
  { status: 'maintenance',  label: 'Maintenance'  },
  { status: 'standby',      label: 'Standby'      },
  { status: 'reconnecting', label: 'Reconnecting' },
  { status: 'unauthorized', label: 'Unauthorized' },
  { status: 'unreachable',  label: 'Unreachable'  },
  { status: 'offline',      label: 'Offline'      },
  { status: 'recovering',   label: 'Recovering'   },
  { status: 'disabled',     label: 'Disabled'     },
]

const PULSE_STATES: CameraStatus[] = ['recording', 'streaming', 'reconnecting', 'recovering']

describe('CameraStatusBadge', () => {
  it.each(ALL_STATES)('renders label "$label" for status "$status"', ({ status, label }) => {
    render(<CameraStatusBadge status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it.each(PULSE_STATES)('applies animate-status-pulse for %s', (status) => {
    const { container } = render(<CameraStatusBadge status={status} />)
    expect(container.querySelector('.animate-status-pulse')).not.toBeNull()
  })

  it.each(
    ALL_STATES.filter(({ status }) => !PULSE_STATES.includes(status)),
  )('does not pulse for $status', ({ status }) => {
    const { container } = render(<CameraStatusBadge status={status} />)
    expect(container.querySelector('.animate-status-pulse')).toBeNull()
  })

  it('has role="status" for accessibility', () => {
    render(<CameraStatusBadge status="offline" />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('accepts className override', () => {
    const { container } = render(<CameraStatusBadge status="connected" className="my-cls" />)
    expect(container.firstChild).toHaveClass('my-cls')
  })
})
