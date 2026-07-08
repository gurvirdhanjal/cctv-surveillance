import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useLiveStore } from '../store/liveStore'
import { AlertTimeline } from './AlertTimeline'
import type { LiveAlert } from '../types'

function makeAlert(id: number, severity: LiveAlert['severity'], minutesAgo: number): LiveAlert {
  const ts = new Date(Date.now() - minutesAgo * 60 * 1000).toISOString()
  return {
    alert_id: id,
    alert_type: 'INTRUSION',
    severity,
    state: 'OPEN',
    camera_id: 1,
    zone_id: null,
    person_id: null,
    triggered_at: ts,
    acknowledged_at: null,
    resolved_at: null,
    suppressed_by_window_id: null,
    dedup_key: null,
    global_track_id: null,
    snapshot_url: null,
    sla_deadline: null,
  }
}

const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
})

describe('AlertTimeline', () => {
  it('renders with fixed 120px height', () => {
    const { container } = render(<AlertTimeline />)
    const root = container.firstChild as HTMLElement
    expect(root.style.height).toBe('120px')
  })

  it('renders marks for alerts in last 60 min only', () => {
    useLiveStore.setState({
      alerts: [
        makeAlert(1, 'CRITICAL', 10),
        makeAlert(2, 'HIGH', 30),
        makeAlert(3, 'LOW', 70),
      ],
    })
    const { container } = render(<AlertTimeline />)
    const marks = container.querySelectorAll('[data-alert-mark]')
    expect(marks).toHaveLength(2)
  })

  it('shows all-clear text when no alerts', () => {
    useLiveStore.setState({ alerts: [] })
    render(<AlertTimeline />)
    expect(screen.getByText(/no alerts/i)).toBeInTheDocument()
  })

  it('calls onSeek with alert id when mark clicked', () => {
    const onSeek = vi.fn()
    useLiveStore.setState({ alerts: [makeAlert(5, 'HIGH', 15)] })
    const { container } = render(<AlertTimeline onSeek={onSeek} />)
    const mark = container.querySelector('[data-alert-mark]') as HTMLElement
    mark.click()
    expect(onSeek).toHaveBeenCalledWith(5)
  })
})
