import * as React from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
  type ColumnFiltersState,
  type VisibilityState,
  type RowSelectionState,
} from '@tanstack/react-table'
import { ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/shared/utils/cn'
import { useTableLayout } from '@/shared/tables/useTableLayout'
import { useAuthStore } from '@/stores/authStore'

const DENSITY_HEIGHTS: Record<string, string> = {
  compact: '32px',
  default: '40px',
  relaxed: '52px',
}

interface DensitySelectorProps {
  value: 'compact' | 'default' | 'relaxed'
  onChange: (v: 'compact' | 'default' | 'relaxed') => void
}

function DensitySelector({ value, onChange }: DensitySelectorProps) {
  const options: Array<{ key: 'compact' | 'default' | 'relaxed'; label: string }> = [
    { key: 'compact', label: 'S' },
    { key: 'default', label: 'M' },
    { key: 'relaxed', label: 'L' },
  ]
  return (
    <div
      role="group"
      aria-label="Row density"
      className="flex items-center rounded-lg border border-border overflow-hidden"
    >
      {options.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          data-density={key}
          onClick={() => onChange(key)}
          className={cn(
            'h-7 w-7 text-[11px] font-medium transition-colors',
            value === key
              ? 'bg-surface-raised text-text-primary'
              : 'bg-surface-base text-text-muted hover:bg-surface-raised',
          )}
          aria-pressed={value === key}
          aria-label={key}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

interface DataTableProps<TData> {
  /** Required stable identifier — used as localStorage key for column/density prefs */
  tableId: string
  columns: ColumnDef<TData, unknown>[]
  data: TData[]
  /** Override density; if omitted, reads from persisted prefs (default: 'default') */
  density?: 'compact' | 'default' | 'relaxed'
  /** Show a global filter input above the table */
  filterPlaceholder?: string
  /** Rows per page; default 20 */
  pageSize?: number
  /** Called when row selection changes */
  onRowSelectionChange?: (rows: TData[]) => void
  /** Called when Enter is pressed on a focused row */
  onRowOpen?: (row: TData) => void
  /** className applied to the outer wrapper */
  className?: string
  /** Empty state content rendered when data is empty */
  emptyContent?: React.ReactNode
}

export function DataTable<TData>({
  tableId,
  columns,
  data,
  density: densityProp,
  filterPlaceholder = 'Filter...',
  pageSize = 20,
  onRowSelectionChange,
  className,
  emptyContent,
}: DataTableProps<TData>) {
  const userId = useAuthStore((s) => s.user?.userId ?? '')
  const layout = useTableLayout(tableId, userId)

  const density = densityProp ?? layout.density

  const [sorting, setSorting] = React.useState<SortingState>([])
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([])
  const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({})
  const [rowSelection, setRowSelection] = React.useState<RowSelectionState>({})
  const [globalFilter, setGlobalFilter] = React.useState('')

  const table = useReactTable({
    data,
    columns,
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      rowSelection,
      globalFilter,
      columnSizing: layout.columnSizing,
      columnOrder: layout.columnOrder.length > 0 ? layout.columnOrder : undefined,
    },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: setRowSelection,
    onGlobalFilterChange: setGlobalFilter,
    onColumnSizingChange: (updater) => {
      const next =
        typeof updater === 'function' ? updater(layout.columnSizing) : updater
      layout.setColumnSizing(next)
    },
    onColumnOrderChange: (updater) => {
      const current = layout.columnOrder.length > 0
        ? layout.columnOrder
        : columns.map((c) => (c as { accessorKey?: string }).accessorKey ?? '')
      const next = typeof updater === 'function' ? updater(current) : updater
      layout.setColumnOrder(next)
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    columnResizeMode: 'onChange',
    initialState: { pagination: { pageSize } },
  })

  React.useEffect(() => {
    if (!onRowSelectionChange) return
    const selected = table.getSelectedRowModel().rows.map((r) => r.original)
    onRowSelectionChange(selected)
  }, [rowSelection, table, onRowSelectionChange])

  return (
    <div
      className={cn('flex flex-col gap-3', className)}
      style={{ '--table-row-h': DENSITY_HEIGHTS[density] } as React.CSSProperties}
    >
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <input
          type="search"
          placeholder={filterPlaceholder}
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          className="h-8 w-64 rounded-lg border border-border bg-surface-base px-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)]"
          aria-label={filterPlaceholder}
        />
        <div className="flex-1" />
        <span className="text-xs text-text-muted">
          {table.getFilteredRowModel().rows.length} row
          {table.getFilteredRowModel().rows.length !== 1 ? 's' : ''}
        </span>
        <DensitySelector value={density} onChange={layout.setDensity} />
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-border">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-surface-raised">
              {table.getHeaderGroups().map((hg) => (
                <tr key={hg.id} className="border-b border-border">
                  {hg.headers.map((header) => {
                    const canSort = header.column.getCanSort()
                    const sorted = header.column.getIsSorted()
                    return (
                      <th
                        key={header.id}
                        colSpan={header.colSpan}
                        style={{ width: header.getSize() }}
                        className={cn(
                          'px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted',
                          canSort && 'cursor-pointer select-none hover:text-text-primary transition-colors',
                        )}
                        onClick={canSort ? header.column.getToggleSortingHandler() : undefined}
                        aria-sort={
                          sorted === 'asc' ? 'ascending' : sorted === 'desc' ? 'descending' : undefined
                        }
                      >
                        <div className="flex items-center gap-1">
                          {header.isPlaceholder
                            ? null
                            : flexRender(header.column.columnDef.header, header.getContext())}
                          {canSort && (
                            <span className="text-text-muted/50">
                              {sorted === 'asc' ? (
                                <ChevronUp className="h-3 w-3" />
                              ) : sorted === 'desc' ? (
                                <ChevronDown className="h-3 w-3" />
                              ) : (
                                <ChevronsUpDown className="h-3 w-3" />
                              )}
                            </span>
                          )}
                        </div>
                        {/* Resize handle */}
                        {header.column.getCanResize() && (
                          <div
                            onMouseDown={header.getResizeHandler()}
                            onTouchStart={header.getResizeHandler()}
                            className="absolute right-0 top-0 h-full w-1 cursor-col-resize bg-border opacity-0 hover:opacity-100"
                          />
                        )}
                      </th>
                    )
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.length === 0 ? (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="py-12 text-center text-sm text-text-muted"
                  >
                    {emptyContent ?? 'No data'}
                  </td>
                </tr>
              ) : (
                table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    data-selected={row.getIsSelected() || undefined}
                    className="border-b border-border last:border-0 hover:bg-surface-sunken data-[selected]:bg-[var(--selected-row)] transition-colors duration-[var(--duration-fast)]"
                    style={{ height: 'var(--table-row-h)' }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 text-text-primary">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {table.getPageCount() > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-text-muted">
            Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
              className="flex h-7 w-7 items-center justify-center rounded-md border border-border text-text-secondary transition-colors hover:bg-surface-sunken disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Previous page"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
              className="flex h-7 w-7 items-center justify-center rounded-md border border-border text-text-secondary transition-colors hover:bg-surface-sunken disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Next page"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
