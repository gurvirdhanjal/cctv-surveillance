import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AlertCard } from './AlertCard'
import type { LiveAlert } from '../types'

function makeAlert(overrides: Partial<LiveAlert> = {}): LiveAlert {
  return {
    alert_id: 1,
    alert_type: 'INTRUSION',
    severity: 'HIGH',
    state: 'OPEN',
    camera_id: 2,
    zone_id: 3,
    person_id: null,
    triggered_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    acknowledged_at: null,
    resolved_at: null,
    suppressed_by_window_id: null,
    dedup_key: null,
    global_track_id: null,
    snapshot_url: null,
    ...overrides,
  }
}

describe('AlertCard', () => {
  it('renders alert type formatted', () => {
    render(<AlertCard alert={makeAlert()} />)
    expect(screen.getByText('Intrusion')).toBeInTheDocument()
  })

  it('renders severity label', () => {
    render(<AlertCard alert={makeAlert({ severity: 'CRITICAL' })} />)
    expect(screen.getByText('CRITICAL')).toBeInTheDocument()
  })

  it('shows severity colour bar element', () => {
    const { container } = render(<AlertCard alert={makeAlert({ severity: 'CRITICAL' })} />)
    const bar = container.querySelector('.bg-severity-critical')
    expect(bar).toBeInTheDocument()
  })

  it('shows camera and zone location', () => {
    render(<AlertCard alert={makeAlert({ camera_id: 2, zone_id: 3 })} />)
    expect(screen.getByText('Cam #2 · Zone #3')).toBeInTheDocument()
  })

  it('calls onAcknowledge with alert_id when Acknowledge clicked', () => {
    const onAck = vi.fn()
    render(<AlertCard alert={makeAlert()} onAcknowledge={onAck} />)
    fireEvent.click(screen.getByText('Acknowledge'))
    expect(onAck).toHaveBeenCalledWith(1)
  })

  it('calls onResolve with alert_id when Resolve clicked', () => {
    const onResolve = vi.fn()
    render(<AlertCard alert={makeAlert()} onResolve={onResolve} />)
    fireEvent.click(screen.getByText('Resolve'))
    expect(onResolve).toHaveBeenCalledWith(1)
  })

  it('hides CTAs for acknowledged alerts', () => {
    render(<AlertCard alert={makeAlert({ state: 'ACKNOWLEDGED' })} />)
    expect(screen.queryByText('Acknowledge')).toBeNull()
    expect(screen.queryByText('Resolve')).toBeNull()
    expect(screen.getByText('ACKNOWLEDGED')).toBeInTheDocument()
  })
})
