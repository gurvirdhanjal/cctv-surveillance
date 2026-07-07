import { useMemo } from 'react'
import {
  useWorkspacePrefs,
  type TableLayoutPrefs,
} from '@/shared/workspace/useWorkspacePrefs'

const DEFAULTS: TableLayoutPrefs = {
  columnOrder: [],
  columnSizing: {},
  columnPinning: { left: [], right: [] },
  density: 'default',
  sorting: [],
}

export function useTableLayout(tableId: string, userId: string) {
  const key = `${tableId}_${userId}`
  const layout = useWorkspacePrefs((s) => s.tableLayouts[key] ?? DEFAULTS)
  const setTableLayout = useWorkspacePrefs((s) => s.setTableLayout)

  const actions = useMemo(
    () => ({
      setDensity: (density: TableLayoutPrefs['density']) =>
        setTableLayout(key, { ...layout, density }),
      setColumnSizing: (columnSizing: Record<string, number>) =>
        setTableLayout(key, { ...layout, columnSizing }),
      setColumnOrder: (columnOrder: string[]) =>
        setTableLayout(key, { ...layout, columnOrder }),
      setColumnPinning: (columnPinning: TableLayoutPrefs['columnPinning']) =>
        setTableLayout(key, { ...layout, columnPinning }),
      setSorting: (sorting: TableLayoutPrefs['sorting']) =>
        setTableLayout(key, { ...layout, sorting }),
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key, setTableLayout],
  )

  return {
    density: layout.density,
    columnOrder: layout.columnOrder,
    columnSizing: layout.columnSizing,
    columnPinning: layout.columnPinning,
    sorting: layout.sorting,
    ...actions,
  }
}
