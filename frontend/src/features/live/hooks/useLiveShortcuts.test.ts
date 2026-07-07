import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useLiveShortcuts } from './useLiveShortcuts'
import { useLiveStore } from '../store/liveStore'
import { useCommandPaletteStore } from '@/stores/commandPaletteStore'
import type { LiveAlert } from '../types'

const initialLive = useLiveStore.getState()
const initialPalette = useCommandPaletteStore.getState()

function makeAlert(id: number): LiveAlert {
  return {
    alert_id: id, alert_type: 'INTRUSION', severity: 'HIGH', state: 'OPEN',
    camera_id: 1, zone_id: null, person_id: null,
    triggered_at: new Date().toISOString(),
    acknowledged_at: null, resolved_at: null,
    suppressed_by_window_id: null, dedup_key: null,
    global_track_id: null, snapshot_url: null,
  }
}

function pressKey(key: string, opts: KeyboardEventInit = {}) {
  window.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, ...opts }))
}

beforeEach(() => {
  useLiveStore.setState(initialLive, true)
  useCommandPaletteStore.setState(initialPalette, true)
})

afterEach(() => vi.restoreAllMocks())

describe('useLiveShortcuts', () => {
  it('A acknowledges first open alert', () => {
    useLiveStore.setState({ alerts: [makeAlert(1)] })
    renderHook(() => useLiveShortcuts())
    pressKey('a')
    expect(useLiveStore.getState().alerts[0].state).toBe('ACKNOWLEDGED')
  })

  it('R resolves first open alert', () => {
    useLiveStore.setState({ alerts: [makeAlert(1)] })
    renderHook(() => useLiveShortcuts())
    pressKey('r')
    expect(useLiveStore.getState().alerts[0].state).toBe('RESOLVED')
  })

  it('B adds a bookmark for the focused camera', () => {
    useLiveStore.setState({ focusedCameraId: 5 })
    renderHook(() => useLiveShortcuts())
    pressKey('b')
    const bookmarks = useLiveStore.getState().bookmarks
    expect(bookmarks).toHaveLength(1)
    expect(bookmarks[0].cameraId).toBe(5)
  })

  it('N advances focused camera to next in list', () => {
    useLiveStore.setState({
      cameras: [
        { camera_id: 1, name: 'C1', capability_tier: 'FULL', status: 'online', is_active: true, snapshotUrl: null },
        { camera_id: 2, name: 'C2', capability_tier: 'FULL', status: 'online', is_active: true, snapshotUrl: null },
      ],
      focusedCameraId: 1,
    })
    renderHook(() => useLiveShortcuts())
    pressKey('n')
    expect(useLiveStore.getState().focusedCameraId).toBe(2)
  })

  it('? calls onToggleLegend', () => {
    const onToggleLegend = vi.fn()
    renderHook(() => useLiveShortcuts({ onToggleLegend }))
    pressKey('?')
    expect(onToggleLegend).toHaveBeenCalledOnce()
  })

  it('E calls onExport', () => {
    const onExport = vi.fn()
    renderHook(() => useLiveShortcuts({ onExport }))
    pressKey('e')
    expect(onExport).toHaveBeenCalledOnce()
  })

  it('ignores shortcuts when typing in an input', () => {
    useLiveStore.setState({ alerts: [makeAlert(1)] })
    renderHook(() => useLiveShortcuts())
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }))
    // alert should NOT be acknowledged since target is input
    expect(useLiveStore.getState().alerts[0].state).toBe('OPEN')
    document.body.removeChild(input)
  })

  it('ignores shortcuts when command palette is open', () => {
    useLiveStore.setState({ alerts: [makeAlert(1)] })
    useCommandPaletteStore.setState({ open: true })
    renderHook(() => useLiveShortcuts())
    pressKey('a')
    // Still OPEN because palette was open
    expect(useLiveStore.getState().alerts[0].state).toBe('OPEN')
  })
})
