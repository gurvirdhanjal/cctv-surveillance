import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { CameraStatusBadge, type CameraStatus } from './CameraStatusBadge'

/** §K closed set — 13 states. */
const ALL_STATES: { status: CameraStatus; label: string }[] = [
  { status: 'online',        label: 'Online'       },
  { status: 'recording',     label: 'Recording'    },
  { status: 'streaming',     label: 'Streaming'    },
  { status: 'analytics',     label: 'Analytics'    },
  { status: 'maintenance',   label: 'Maintenance'  },
  { status: 'updating',      label: 'Updating'     },
  { status: 'initializing',  label: 'Initializing' },
  { status: 'disconnected',  label: 'Disconnected' },
  { status: 'unauthorized',  label: 'Unauthorized' },
  { status: 'syncing',       label: 'Syncing'      },
  { status: 'calibrating',   label: 'Calibrating'  },
  { status: 'training',      label: 'Training'     },
  { status: 'importing',     label: 'Importing'    },
]

describe('CameraStatusBadge §K (13 states)', () => {
  it.each(ALL_STATES)('renders label "$label" for status "$status"', ({ status, label }) => {
    render(<CameraStatusBadge status={status} />)
    expect(screen.getByText(label)).toBeInTheDocument()
  })

  it('has role="status" for accessibility', () => {
    render(<CameraStatusBadge status="online" />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('has aria-label matching the status label', () => {
    render(<CameraStatusBadge status="calibrating" />)
    expect(screen.getByRole('status', { name: 'Calibrating' })).toBeInTheDocument()
  })

  it('training uses violet color token', () => {
    const { container } = render(<CameraStatusBadge status="training" />)
    expect((container.firstElementChild as HTMLElement).className).toMatch(/violet/)
  })

  it('calibrating uses teal color token', () => {
    const { container } = render(<CameraStatusBadge status="calibrating" />)
    expect((container.firstElementChild as HTMLElement).className).toMatch(/teal/)
  })

  it('unauthorized uses orange color token', () => {
    const { container } = render(<CameraStatusBadge status="unauthorized" />)
    expect((container.firstElementChild as HTMLElement).className).toMatch(/orange/)
  })

  it('covers exactly 13 states', () => {
    expect(ALL_STATES).toHaveLength(13)
  })

  it('accepts className override', () => {
    const { container } = render(<CameraStatusBadge status="online" className="my-cls" />)
    expect(container.firstChild).toHaveClass('my-cls')
  })
})
