import { describe, it, expect, beforeEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import {
  useWorkspacePrefs,
  RECENT_CAMERAS_MAX,
  CMDK_RECENTS_MAX,
} from './useWorkspacePrefs'

const DEFAULT_TABLE_LAYOUT = {
  columnOrder: [],
  columnSizing: {},
  columnPinning: { left: [], right: [] },
  density: 'default' as const,
  sorting: [],
}

beforeEach(() => {
  localStorage.clear()
  // Reset only data fields; do NOT pass `true` (replace) — that would wipe action functions
  useWorkspacePrefs.setState({
    version: 1,
    tableLayouts: {},
    workspaceThemes: {},
    sidebarOpen: true,
    favoriteCameraIds: [],
    defaultGridLayout: '3x3',
    recentCameraIds: [],
    pinnedAlertIds: [],
    treeExpansion: {},
    treeOrder: {},
    cmdkRecents: [],
    panelLayouts: {},
  })
})

describe('useWorkspacePrefs exports (§R)', () => {
  it('RECENT_CAMERAS_MAX = 10', () => {
    expect(RECENT_CAMERAS_MAX).toBe(10)
  })

  it('CMDK_RECENTS_MAX = 8', () => {
    expect(CMDK_RECENTS_MAX).toBe(8)
  })
})

describe('useWorkspacePrefs actions (§R)', () => {
  it('pushRecentCamera caps recentCameraIds at 10 (FIFO eviction)', () => {
    const { result } = renderHook(() => useWorkspacePrefs())

    act(() => {
      for (let i = 1; i <= 11; i++) {
        result.current.pushRecentCamera(i)
      }
    })

    expect(result.current.recentCameraIds).toHaveLength(10)
    // Newest first; oldest (id=1) evicted
    expect(result.current.recentCameraIds[0]).toBe(11)
    expect(result.current.recentCameraIds).not.toContain(1)
  })

  it('pushRecentCamera deduplicates (existing id moves to front)', () => {
    const { result } = renderHook(() => useWorkspacePrefs())

    act(() => {
      result.current.pushRecentCamera(5)
      result.current.pushRecentCamera(6)
      result.current.pushRecentCamera(5) // re-push id=5
    })

    expect(result.current.recentCameraIds[0]).toBe(5)
    expect(result.current.recentCameraIds.filter((x) => x === 5)).toHaveLength(1)
  })

  it('setWorkspaceTheme persists per workspace', () => {
    const { result } = renderHook(() => useWorkspacePrefs())

    act(() => {
      result.current.setWorkspaceTheme('analytics', 'dark')
    })

    expect(result.current.workspaceThemes['analytics']).toBe('dark')
  })

  it('setTableLayout merges onto existing layout', () => {
    const { result } = renderHook(() => useWorkspacePrefs())

    act(() => {
      result.current.setTableLayout('admin-users', { ...DEFAULT_TABLE_LAYOUT, density: 'compact' })
    })

    act(() => {
      result.current.setTableLayout('admin-users', { density: 'relaxed' })
    })

    expect(result.current.tableLayouts['admin-users'].density).toBe('relaxed')
  })

  it('toggleFavoriteCamera adds then removes', () => {
    const { result } = renderHook(() => useWorkspacePrefs())

    act(() => { result.current.toggleFavoriteCamera(42) })
    expect(result.current.favoriteCameraIds).toContain(42)

    act(() => { result.current.toggleFavoriteCamera(42) })
    expect(result.current.favoriteCameraIds).not.toContain(42)
  })
})

describe('useWorkspacePrefs PII guard (§R)', () => {
  it('initial state contains no sensitive keys', () => {
    const { result } = renderHook(() => useWorkspacePrefs())
    const state = result.current
    const keys = Object.keys(state)
    const forbidden = ['token', 'rtsp_url', 'password', 'jwt', 'secret']
    for (const f of forbidden) {
      expect(keys).not.toContain(f)
    }
  })
})

describe('useWorkspacePrefs persistence (§R)', () => {
  it('writes to localStorage after action', () => {
    const { result } = renderHook(() => useWorkspacePrefs())

    act(() => {
      result.current.setWorkspaceTheme('operator', 'dark')
    })

    const raw = localStorage.getItem('vms.workspace')
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw!)
    expect(parsed.state.workspaceThemes['operator']).toBe('dark')
  })

  it('rehydrates via persist.rehydrate() after localStorage is set', async () => {
    const saved = JSON.stringify({
      state: {
        version: 1,
        tableLayouts: {},
        workspaceThemes: { analytics: 'dark' },
        sidebarOpen: false,
        favoriteCameraIds: [5, 6],
        defaultGridLayout: '4x4',
        recentCameraIds: [5],
        pinnedAlertIds: [],
        treeExpansion: {},
        treeOrder: {},
        cmdkRecents: [],
        panelLayouts: {},
      },
      version: 1,
    })
    localStorage.setItem('vms.workspace', saved)
    await act(async () => {
      await useWorkspacePrefs.persist.rehydrate()
    })
    const state = useWorkspacePrefs.getState()
    expect(state.workspaceThemes['analytics']).toBe('dark')
    expect(state.favoriteCameraIds).toContain(5)
  })

  it('migrate coerces version-0 unknown data without throwing', async () => {
    const stale = JSON.stringify({ state: { someOldKey: true }, version: 0 })
    localStorage.setItem('vms.workspace', stale)
    await expect(
      act(async () => { await useWorkspacePrefs.persist.rehydrate() })
    ).resolves.not.toThrow()
  })
})
