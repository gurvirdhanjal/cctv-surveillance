import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ColumnDef } from '@tanstack/react-table'
import { useWorkspacePrefs } from '@/shared/workspace/useWorkspacePrefs'
import { DataTable } from './DataTable'

interface Row { id: number; name: string; status: string }

const columns: ColumnDef<Row, unknown>[] = [
  { id: 'select', header: 'Select', cell: () => null },
  { accessorKey: 'id', header: 'ID', enableResizing: true },
  { accessorKey: 'name', header: 'Name', enableResizing: true },
  { accessorKey: 'status', header: 'Status' },
]

const makeData = (n: number): Row[] =>
  Array.from({ length: n }, (_, i) => ({ id: i + 1, name: `Item ${i + 1}`, status: 'ok' }))

beforeEach(() => {
  localStorage.clear()
  useWorkspacePrefs.setState({
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

describe('DataTable v3 — keyboard nav (§D)', () => {
  it('↓ then Enter calls onRowOpen with the row', () => {
    const onRowOpen = vi.fn()
    const data = makeData(3)
    const { container } = render(
      <DataTable tableId="test" columns={columns} data={data} onRowOpen={onRowOpen} />
    )
    const grid = container.querySelector('[role="grid"]')
    expect(grid).not.toBeNull()
    fireEvent.keyDown(grid!, { key: 'ArrowDown' })
    fireEvent.keyDown(grid!, { key: 'Enter' })
    expect(onRowOpen).toHaveBeenCalledWith(data[0])
  })

  it('Space toggles row selection on the active row', () => {
    const onSel = vi.fn()
    const data = makeData(3)
    const { container } = render(
      <DataTable
        tableId="test"
        columns={columns}
        data={data}
        onRowSelectionChange={onSel}
      />
    )
    const grid = container.querySelector('[role="grid"]')!
    fireEvent.keyDown(grid, { key: 'ArrowDown' })
    fireEvent.keyDown(grid, { key: ' ' })
    // onRowSelectionChange called with the selected row
    expect(onSel).toHaveBeenCalled()
  })

  it('table root has role="grid" and tabIndex=0', () => {
    const { container } = render(
      <DataTable tableId="test" columns={columns} data={makeData(2)} />
    )
    const grid = container.querySelector('[role="grid"]')
    expect(grid).not.toBeNull()
    expect((grid as HTMLElement).tabIndex).toBe(0)
  })
})

describe('DataTable v3 — bulk actions (§D)', () => {
  it('BulkActionsToolbar hidden when 0 rows selected', () => {
    render(
      <DataTable
        tableId="test"
        columns={columns}
        data={makeData(3)}
        bulkActions={[{ label: 'Delete', icon: null, onClick: vi.fn() }]}
      />
    )
    expect(screen.queryByRole('toolbar', { name: /bulk/i })).toBeNull()
  })

  it('BulkActionsToolbar visible when ≥1 rows selected', () => {
    const data = makeData(3)
    const { container } = render(
      <DataTable
        tableId="test"
        columns={columns}
        data={data}
        bulkActions={[{ label: 'Delete', icon: null, onClick: vi.fn() }]}
      />
    )
    const grid = container.querySelector('[role="grid"]')!
    // Select first row via keyboard
    fireEvent.keyDown(grid, { key: 'ArrowDown' })
    fireEvent.keyDown(grid, { key: ' ' })
    const toolbar = container.querySelector('[data-bulk-toolbar]')
    expect(toolbar).not.toBeNull()
  })
})

describe('DataTable v3 — virtualization (§D)', () => {
  it('mounts Virtuoso for >100 rows', () => {
    const { container } = render(
      <DataTable tableId="test" columns={columns} data={makeData(101)} />
    )
    // DataTable sets data-virtuoso="" on the grid wrapper when using Virtuoso
    expect(container.querySelector('[data-virtuoso]')).not.toBeNull()
  })

  it('does NOT mount Virtuoso for ≤100 rows', () => {
    const { container } = render(
      <DataTable tableId="test" columns={columns} data={makeData(50)} />
    )
    expect(container.querySelector('[data-virtuoso]')).toBeNull()
  })
})
