import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CameraTree } from './CameraTree'
import { useLiveStore } from '../store/liveStore'
import type { CameraState } from '../types'

vi.mock('../hooks/useCameraSnapshot', () => ({
  useCameraSnapshot: () => null,
}))

vi.mock('./GridLayoutSelector', () => ({
  GridLayoutSelector: () => <div data-testid="grid-selector" />,
}))

const initial = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initial, true)
})

function makeCamera(id: number, name = `Cam ${id}`): CameraState {
  return {
    camera_id: id, name, capability_tier: 'FULL',
    status: 'online', is_active: true, snapshotUrl: null,
  }
}

describe('CameraTree', () => {
  it('renders camera tiles', () => {
    useLiveStore.setState({ cameras: [makeCamera(1), makeCamera(2), makeCamera(3)] })
    render(<CameraTree />)
    expect(screen.getAllByRole('button', { name: /Focus camera/ })).toHaveLength(3)
  })

  it('shows 12 tiles per page when > 12 cameras', () => {
    const cams = Array.from({ length: 14 }, (_, i) => makeCamera(i + 1))
    useLiveStore.setState({ cameras: cams })
    render(<CameraTree />)
    expect(screen.getAllByRole('button', { name: /Focus camera/ })).toHaveLength(12)
  })

  it('pager advances to show remaining tiles', () => {
    const cams = Array.from({ length: 14 }, (_, i) => makeCamera(i + 1))
    useLiveStore.setState({ cameras: cams })
    render(<CameraTree />)
    fireEvent.click(screen.getByLabelText('Next page'))
    expect(screen.getAllByRole('button', { name: /Focus camera/ })).toHaveLength(2)
  })

  it('clicking a tile sets focusedCameraId', () => {
    useLiveStore.setState({ cameras: [makeCamera(1), makeCamera(2)] })
    render(<CameraTree />)
    fireEvent.click(screen.getByLabelText('Focus camera Cam 2'))
    expect(useLiveStore.getState().focusedCameraId).toBe(2)
  })

  it('focused tile has ring-white/40 class', () => {
    useLiveStore.setState({ cameras: [makeCamera(1)], focusedCameraId: 1 })
    render(<CameraTree />)
    const tile = screen.getByLabelText('Focus camera Cam 1')
    expect(tile.className).toContain('ring-white/40')
  })

  it('alarming tile has border-[#dc2626] class', () => {
    useLiveStore.setState({
      cameras: [makeCamera(1)],
      alerts: [{
        alert_id: 1, alert_type: 'INTRUSION', severity: 'CRITICAL', state: 'OPEN',
        camera_id: 1, zone_id: null, person_id: null,
        triggered_at: new Date().toISOString(),
        acknowledged_at: null, resolved_at: null,
        suppressed_by_window_id: null, dedup_key: null,
        global_track_id: null, snapshot_url: null,
      }],
    })
    render(<CameraTree />)
    const tile = screen.getByLabelText('Focus camera Cam 1')
    expect(tile.className).toContain('border-[#dc2626]')
  })

  it('search filters tiles by name', () => {
    useLiveStore.setState({ cameras: [makeCamera(1, 'Main Entrance'), makeCamera(2, 'Warehouse')] })
    render(<CameraTree />)
    fireEvent.change(screen.getByLabelText('Search cameras'), { target: { value: 'Main' } })
    expect(screen.getAllByRole('button', { name: /Focus camera/ })).toHaveLength(1)
    expect(screen.getByLabelText('Focus camera Main Entrance')).toBeInTheDocument()
  })
})
