import { describe, it, expect, beforeEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useWorkspacePrefs } from '@/shared/workspace/useWorkspacePrefs'
import { useTableLayout } from './useTableLayout'

beforeEach(() => {
  localStorage.clear()
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

describe('useTableLayout (§D)', () => {
  it('returns default density "default"', () => {
    const { result } = renderHook(() => useTableLayout('test-table', 'user1'))
    expect(result.current.density).toBe('default')
  })

  it('setDensity updates density in prefs store', () => {
    const { result } = renderHook(() => useTableLayout('test-table', 'user1'))

    act(() => { result.current.setDensity('compact') })

    expect(result.current.density).toBe('compact')
    const stored = useWorkspacePrefs.getState().tableLayouts['test-table_user1']
    expect(stored?.density).toBe('compact')
  })

  it('setColumnSizing updates sizing', () => {
    const { result } = renderHook(() => useTableLayout('test-table', 'user1'))

    act(() => { result.current.setColumnSizing({ name: 200, status: 80 }) })

    expect(result.current.columnSizing).toEqual({ name: 200, status: 80 })
  })

  it('setColumnOrder updates order', () => {
    const { result } = renderHook(() => useTableLayout('test-table', 'user1'))

    act(() => { result.current.setColumnOrder(['status', 'name', 'actions']) })

    expect(result.current.columnOrder).toEqual(['status', 'name', 'actions'])
  })

  it('different tableId_userId keys are independent', () => {
    const { result: r1 } = renderHook(() => useTableLayout('cameras', 'alice'))
    const { result: r2 } = renderHook(() => useTableLayout('persons', 'alice'))

    act(() => { r1.current.setDensity('compact') })

    expect(r1.current.density).toBe('compact')
    expect(r2.current.density).toBe('default')
  })

  it('persists to localStorage (written to vms.workspace)', () => {
    const { result } = renderHook(() => useTableLayout('audit-log', 'user1'))

    act(() => { result.current.setDensity('relaxed') })

    const raw = localStorage.getItem('vms.workspace')
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw!)
    expect(parsed.state.tableLayouts['audit-log_user1'].density).toBe('relaxed')
  })
})
