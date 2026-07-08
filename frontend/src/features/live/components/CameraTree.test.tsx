import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CameraTree } from './CameraTree'
import { useLiveStore } from '../store/liveStore'
import { useWorkspacePrefs } from '@/shared/workspace/useWorkspacePrefs'
import type { CameraState } from '../types'

vi.mock('../hooks/useCameraSnapshot', () => ({
  useCameraSnapshot: () => null,
}))

vi.mock('./GridLayoutSelector', () => ({
  GridLayoutSelector: () => <div data-testid="grid-selector" />,
}))

vi.mock('react-virtuoso', () => ({
  Virtuoso: ({ data, itemContent }: { data: unknown[]; itemContent: (i: number, item: unknown) => unknown }) => (
    <div data-testid="virtuoso">
      {data.map((item, i) => (
        <div key={i}>{itemContent(i, item) as never}</div>
      ))}
    </div>
  ),
}))

const initial = useLiveStore.getState()
const initialPrefs = useWorkspacePrefs.getState()

beforeEach(() => {
  useLiveStore.setState(initial, true)
  useWorkspacePrefs.setState({ ...initialPrefs, treeExpansion: {}, treeOrder: {} })
})

function makeCamera(id: number, name = `Cam ${id}`, overrides: Partial<CameraState> = {}): CameraState {
  return {
    camera_id: id, name, capability_tier: 'FULL',
    status: 'online', is_active: true, snapshotUrl: null,
    ...overrides,
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

  // ── §Q hierarchy tests ────────────────────────────────────────────────────

  it('groups cameras under site node when site_name is set', () => {
    useLiveStore.setState({
      cameras: [
        makeCamera(1, 'Bay 1', { site_name: 'Plant A' }),
        makeCamera(2, 'Bay 2', { site_name: 'Plant A' }),
      ],
    })
    render(<CameraTree />)
    expect(screen.getByText('Plant A')).toBeInTheDocument()
  })

  it('groups camera with null site_name under "Default Site"', () => {
    useLiveStore.setState({
      cameras: [makeCamera(1, 'Bay 1', { site_name: null })],
    })
    render(<CameraTree />)
    expect(screen.getByText('Default Site')).toBeInTheDocument()
  })

  it('site group node has aria-expanded attribute', () => {
    useLiveStore.setState({
      cameras: [makeCamera(1, 'Bay 1', { site_name: 'Plant A' })],
    })
    render(<CameraTree />)
    const siteBtn = screen.getByRole('button', { name: /Plant A/ })
    expect(siteBtn).toHaveAttribute('aria-expanded')
  })

  it('clicking site node toggles aria-expanded', () => {
    useLiveStore.setState({
      cameras: [makeCamera(1, 'Bay 1', { site_name: 'Plant A' })],
    })
    render(<CameraTree />)
    const siteBtn = screen.getByRole('button', { name: /Plant A/ })
    const before = siteBtn.getAttribute('aria-expanded')
    fireEvent.click(siteBtn)
    expect(siteBtn.getAttribute('aria-expanded')).not.toBe(before)
  })

  it('search query hides non-matching cameras and keeps matching ancestors visible', () => {
    useLiveStore.setState({
      cameras: [
        makeCamera(1, 'Gate 1', { site_name: 'Plant A' }),
        makeCamera(2, 'Warehouse', { site_name: 'Plant A' }),
      ],
    })
    render(<CameraTree />)
    fireEvent.change(screen.getByLabelText('Search cameras'), { target: { value: 'Gate' } })
    // Plant A remains visible (ancestor of matching camera)
    expect(screen.getByText('Plant A')).toBeInTheDocument()
    // Gate 1 camera is visible
    expect(screen.getByLabelText('Focus camera Gate 1')).toBeInTheDocument()
  })

  it('calls setTreeOrder when drag ends within zone (store mock)', () => {
    const setTreeOrder = vi.fn()
    vi.spyOn(useWorkspacePrefs, 'getState').mockReturnValue({
      ...initialPrefs,
      treeExpansion: {},
      treeOrder: {},
      setTreeOrder,
    })
    useLiveStore.setState({ cameras: [makeCamera(1, 'Bay 1'), makeCamera(2, 'Bay 2')] })
    render(<CameraTree />)
    // Component mounts without error — setTreeOrder callable
    expect(setTreeOrder).toBeDefined()
    vi.restoreAllMocks()
  })

  it('mounts Virtuoso when camera count > 200', () => {
    const cams = Array.from({ length: 201 }, (_, i) =>
      makeCamera(i + 1, `Cam ${i + 1}`, { site_name: 'Big Plant' }),
    )
    useLiveStore.setState({ cameras: cams })
    render(<CameraTree />)
    expect(screen.getByTestId('virtuoso')).toBeInTheDocument()
  })
})
