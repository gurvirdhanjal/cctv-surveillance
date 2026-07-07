import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AlarmCard } from './AlarmCard'
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

describe('AlarmCard', () => {
  it('renders alert type formatted', () => {
    render(<AlarmCard alert={makeAlert()} />)
    expect(screen.getByText('Intrusion')).toBeInTheDocument()
  })

  it('renders severity label', () => {
    render(<AlarmCard alert={makeAlert({ severity: 'CRITICAL' })} />)
    expect(screen.getByText('CRITICAL')).toBeInTheDocument()
  })

  it('critical card has the alarm-red left border class', () => {
    const { container } = render(<AlarmCard alert={makeAlert({ severity: 'CRITICAL' })} />)
    const card = container.querySelector('[role="article"]')
    expect(card?.className).toContain('border-l-[#dc2626]')
  })

  it('shows camera label', () => {
    render(<AlarmCard alert={makeAlert({ camera_id: 2 })} />)
    expect(screen.getByText('Cam #2')).toBeInTheDocument()
  })

  it('calls onAcknowledge when Acknowledge clicked', () => {
    const onAck = vi.fn()
    render(<AlarmCard alert={makeAlert()} onAcknowledge={onAck} />)
    fireEvent.click(screen.getByText('Acknowledge'))
    expect(onAck).toHaveBeenCalledWith(1)
  })

  it('calls onResolve when Resolve clicked', () => {
    const onResolve = vi.fn()
    render(<AlarmCard alert={makeAlert()} onResolve={onResolve} />)
    fireEvent.click(screen.getByText('Resolve'))
    expect(onResolve).toHaveBeenCalledWith(1)
  })

  it('hides action buttons for non-OPEN alert', () => {
    render(<AlarmCard alert={makeAlert({ state: 'ACKNOWLEDGED' })} />)
    expect(screen.queryByText('Acknowledge')).toBeNull()
    expect(screen.queryByText('Resolve')).toBeNull()
    expect(screen.getByText('ACKNOWLEDGED')).toBeInTheDocument()
  })

  describe('SLA bar', () => {
    beforeEach(() => vi.useFakeTimers())
    afterEach(() => vi.useRealTimers())

    it('does not render SLA bar when sla_deadline is absent', () => {
      const { container } = render(<AlarmCard alert={makeAlert()} />)
      expect(container.querySelector('[role="progressbar"]')).toBeNull()
    })

    it('renders SLA bar when sla_deadline is set', () => {
      const deadline = new Date(Date.now() + 600_000).toISOString()
      render(<AlarmCard alert={makeAlert({ sla_deadline: deadline })} />)
      expect(screen.getByRole('progressbar')).toBeInTheDocument()
    })

    it('SLA bar fill is amber when fraction ≤ 25%', () => {
      // 224s remaining out of 900s = 24.9% → warn
      const deadline = new Date(Date.now() + 224_000).toISOString()
      const { container } = render(
        <AlarmCard alert={makeAlert({ sla_deadline: deadline })} />,
      )
      const fill = container.querySelector('[role="progressbar"]')
      expect(fill?.className).toContain('bg-amber-500')
    })

    it('SLA bar fill is alarm-red when fraction ≤ 10%', () => {
      // 89s remaining out of 900s = 9.9% → crit
      const deadline = new Date(Date.now() + 89_000).toISOString()
      const { container } = render(
        <AlarmCard alert={makeAlert({ sla_deadline: deadline })} />,
      )
      const fill = container.querySelector('[role="progressbar"]')
      expect(fill?.className).toContain('bg-[#dc2626]')
    })
  })

  it('shows +N similar trigger when similarAlerts provided', () => {
    const similar = [makeAlert({ alert_id: 2 }), makeAlert({ alert_id: 3 })]
    render(<AlarmCard alert={makeAlert()} similarAlerts={similar} />)
    expect(screen.getByText('+2 similar')).toBeInTheDocument()
  })

  it('expands similar alerts on trigger click', () => {
    const similar = [makeAlert({ alert_id: 2, alert_type: 'LOITERING' })]
    render(<AlarmCard alert={makeAlert()} similarAlerts={similar} />)
    expect(screen.queryByText('Loitering — just now')).toBeNull()
    fireEvent.click(screen.getByText('+1 similar'))
    expect(screen.getByText(/Loitering/)).toBeInTheDocument()
  })

  it('applies ring-2 ring-action-600 when isSelected', () => {
    const { container } = render(<AlarmCard alert={makeAlert()} isSelected />)
    const card = container.querySelector('[role="article"]')
    expect(card?.className).toContain('ring-action-600')
  })
})
