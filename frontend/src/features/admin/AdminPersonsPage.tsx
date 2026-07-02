import { useRef, useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { api } from '@/shared/api/client'
import type { PersonResponse } from '@/shared/api/types'
import { EnrolmentWizard } from './components/EnrolmentWizard'
import { GdprDeleteDialog } from './components/GdprDeleteDialog'

const TIER_BADGE: Record<string, string> = {
  FULL: 'bg-brand-100 text-brand-700',
  MID: 'bg-yellow-100 text-yellow-800',
  LOW: 'bg-surface-sunken text-text-muted',
}

type PersonExt = PersonResponse & { role?: string }

export function AdminPersonsPage() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [showEnrol, setShowEnrol] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<PersonExt | null>(null)
  const parentRef = useRef<HTMLDivElement>(null)

  const { data, isLoading, isError } = useQuery<PersonResponse[]>({
    queryKey: ['admin', 'persons', search],
    queryFn: () =>
      api.get(
        `/api/persons?limit=500${search.trim() ? `&q=${encodeURIComponent(search.trim())}` : ''}`,
      ),
  })

  const persons = data ?? []

  const rowVirtualizer = useVirtualizer({
    count: persons.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 52,
    overscan: 5,
  })

  return (
    <>
      <Helmet title="Persons — Admin" />
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-[22px] font-semibold text-text-primary">Persons</h1>
          <button
            type="button"
            onClick={() => setShowEnrol(true)}
            className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600"
          >
            Enrol Person
          </button>
        </div>

        <input
          type="search"
          aria-label="Search persons"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name or employee ID…"
          className="mb-4 w-full max-w-sm border border-border rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-500"
        />

        {isLoading && (
          <p role="status" aria-label="Loading persons">
            Loading…
          </p>
        )}
        {isError && (
          <p role="alert" className="text-error text-[14px]">
            Failed to load persons.
          </p>
        )}

        {!isLoading && !isError && (
          <div className="rounded border border-border overflow-hidden">
            <table className="w-full text-[14px]">
              <thead className="bg-surface-sunken border-b border-border">
                <tr>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-muted uppercase tracking-wide">
                    Name
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-muted uppercase tracking-wide">
                    Employee ID
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-muted uppercase tracking-wide">
                    Status
                  </th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
            </table>
            <div
              ref={parentRef}
              className="overflow-auto"
              style={{ height: Math.min(persons.length * 52, 520) }}
            >
              <div style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
                {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                  const p = persons[virtualRow.index]
                  return (
                    <div
                      key={virtualRow.key}
                      data-index={virtualRow.index}
                      ref={rowVirtualizer.measureElement}
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        transform: `translateY(${virtualRow.start}px)`,
                      }}
                      className="flex items-center px-4 py-3 border-b border-border hover:bg-surface-raised"
                    >
                      <span className="flex-1 font-medium text-text-primary">{p.name}</span>
                      <span className="w-36 font-mono text-text-secondary">{p.employee_id}</span>
                      <span className="w-24">
                        <span
                          className={`inline-block px-2 py-0.5 rounded text-[11px] font-medium ${
                            p.is_active
                              ? TIER_BADGE['FULL']
                              : 'bg-surface-sunken text-text-muted'
                          }`}
                        >
                          {p.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </span>
                      <button
                        type="button"
                        aria-label={`Delete ${p.name}`}
                        onClick={() => setDeleteTarget(p)}
                        className="px-3 py-1 text-[12px] text-error hover:text-red-700 hover:bg-red-50 rounded"
                      >
                        Delete
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
            {persons.length === 0 && (
              <p className="px-4 py-6 text-[14px] text-text-muted text-center">
                No persons found.
              </p>
            )}
          </div>
        )}
      </div>

      {showEnrol && (
        <EnrolmentWizard
          onDone={() => {
            setShowEnrol(false)
            void queryClient.invalidateQueries({ queryKey: ['admin', 'persons'] })
          }}
          onCancel={() => setShowEnrol(false)}
        />
      )}

      {deleteTarget && (
        <GdprDeleteDialog
          personId={deleteTarget.person_id}
          personName={deleteTarget.name}
          onConfirmed={() => {
            setDeleteTarget(null)
            void queryClient.invalidateQueries({ queryKey: ['admin', 'persons'] })
          }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </>
  )
}
