import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import axe from 'axe-core'
import React from 'react'
import { AlertCard } from './AlertCard'
import { AlertSidebar } from './AlertSidebar'
import { useLiveStore } from '../store/liveStore'
import type { LiveAlert } from '../types'

vi.mock('@/shared/api/client', () => ({
  api: { get: vi.fn(), patch: vi.fn() },
}))

const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
})

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

function Wrapper({ children }: React.PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return React.createElement(QueryClientProvider, { client: qc }, children)
}

describe('AlertCard a11y', () => {
  it('open alert with action buttons has no violations', async () => {
    const { container } = render(
      <AlertCard alert={makeAlert()} onAcknowledge={vi.fn()} onResolve={vi.fn()} />,
    )
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })

  it('acknowledged alert has no violations', async () => {
    const { container } = render(
      <AlertCard alert={makeAlert({ state: 'ACKNOWLEDGED' })} />,
    )
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })

  it('critical alert has no violations', async () => {
    const { container } = render(
      <AlertCard
        alert={makeAlert({ severity: 'CRITICAL', alert_type: 'PPE_VIOLATION' })}
        onAcknowledge={vi.fn()}
      />,
    )
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })

  it('alert with camera name has no violations', async () => {
    const { container } = render(
      <AlertCard
        alert={makeAlert()}
        cameraName="Main Entrance"
        onAcknowledge={vi.fn()}
        onResolve={vi.fn()}
      />,
    )
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })
})

describe('AlertSidebar a11y', () => {
  it('empty state has no violations', async () => {
    const { container } = render(<AlertSidebar />, { wrapper: Wrapper })
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })

  it('alert list has no violations', async () => {
    useLiveStore.setState({
      alerts: [
        makeAlert({ alert_id: 1, severity: 'CRITICAL' }),
        makeAlert({ alert_id: 2, severity: 'HIGH' }),
        makeAlert({ alert_id: 3, severity: 'MEDIUM', state: 'ACKNOWLEDGED' }),
      ],
    })
    const { container } = render(<AlertSidebar />, { wrapper: Wrapper })
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })

  it('grouped alerts have no violations', async () => {
    useLiveStore.setState({
      alerts: [
        makeAlert({ alert_id: 1, global_track_id: 'gid-abc' }),
        makeAlert({ alert_id: 2, global_track_id: 'gid-abc' }),
      ],
    })
    const { container } = render(<AlertSidebar />, { wrapper: Wrapper })
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })

  it('degraded banner has no violations', async () => {
    useLiveStore.setState({ degraded: { connection: 'lost' } })
    const { container } = render(<AlertSidebar />, { wrapper: Wrapper })
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })
})
