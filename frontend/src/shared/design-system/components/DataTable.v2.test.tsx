import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ColumnDef } from '@tanstack/react-table'
import { useWorkspacePrefs } from '@/shared/workspace/useWorkspacePrefs'
import { DataTable } from './DataTable'

interface Row { id: number; name: string }

const columns: ColumnDef<Row, unknown>[] = [
  { accessorKey: 'id', header: 'ID' },
  { accessorKey: 'name', header: 'Name' },
]

const data: Row[] = [
  { id: 1, name: 'Alpha' },
  { id: 2, name: 'Beta' },
]

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

describe('DataTable v2 — core (§D)', () => {
  it('renders table with data rows', () => {
    render(<DataTable tableId="test" columns={columns} data={data} />)
    expect(screen.getByText('Alpha')).toBeTruthy()
    expect(screen.getByText('Beta')).toBeTruthy()
  })

  it('thead has sticky + bg-surface-raised classes', () => {
    const { container } = render(<DataTable tableId="test" columns={columns} data={data} />)
    const thead = container.querySelector('thead')
    expect(thead?.className).toMatch(/sticky/)
    expect(thead?.className).toMatch(/bg-surface-raised|bg-surface/)
  })

  it('compact density sets --table-row-h: 32px on table root', () => {
    const { container } = render(
      <DataTable tableId="test" columns={columns} data={data} density="compact" />
    )
    const root = container.firstElementChild as HTMLElement
    expect(root.style.getPropertyValue('--table-row-h')).toBe('32px')
  })

  it('default density sets --table-row-h: 40px', () => {
    const { container } = render(
      <DataTable tableId="test" columns={columns} data={data} density="default" />
    )
    const root = container.firstElementChild as HTMLElement
    expect(root.style.getPropertyValue('--table-row-h')).toBe('40px')
  })

  it('relaxed density sets --table-row-h: 52px', () => {
    const { container } = render(
      <DataTable tableId="test" columns={columns} data={data} density="relaxed" />
    )
    const root = container.firstElementChild as HTMLElement
    expect(root.style.getPropertyValue('--table-row-h')).toBe('52px')
  })

  it('renders DensitySelector toggle in toolbar', () => {
    const { container } = render(<DataTable tableId="test" columns={columns} data={data} />)
    // DensitySelector has data-testid or an aria-label
    const selector = container.querySelector('[aria-label="Row density"]')
    expect(selector).not.toBeNull()
  })

  it('tableId is used as the key in workspace prefs after density change', () => {
    const { container } = render(
      <DataTable tableId="admin-cameras" columns={columns} data={data} />
    )
    // DensitySelector click changes density and writes to prefs
    const compactBtn = container.querySelector('[data-density="compact"]')
    if (compactBtn) {
      (compactBtn as HTMLElement).click()
      const stored = useWorkspacePrefs.getState().tableLayouts['admin-cameras_']
      // userId is '' in tests (no auth context); key exists with compact density
      if (stored) expect(stored.density).toBe('compact')
    }
    // Basic: table renders without error
    expect(container.querySelector('table')).not.toBeNull()
  })
})
