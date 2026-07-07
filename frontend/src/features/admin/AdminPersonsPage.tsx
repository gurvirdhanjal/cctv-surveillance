import { useRef, useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Users, Plus } from 'lucide-react'
import { api } from '@/shared/api/client'
import type { PersonResponse } from '@/shared/api/types'
import { EnrolmentWizard } from './components/EnrolmentWizard'
import { GdprDeleteDialog } from './components/GdprDeleteDialog'
import { EmptyState } from './components/EmptyState'
import { Button } from '@/shared/design-system/components/Button'
import { PageHeader } from '@/shared/design-system/components/PageHeader'
import { SkeletonTable } from '@/shared/design-system/components/Skeleton'

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
        <PageHeader
          title="Persons"
          actions={
            <Button onClick={() => setShowEnrol(true)} icon={<Plus className="h-4 w-4" aria-hidden="true" />}>
              Enrol Person
            </Button>
          }
        />

        <input
          type="search"
          aria-label="Search persons"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name or employee ID…"
          className="mb-5 h-10 w-full max-w-sm rounded-[10px] border border-border bg-surface-base px-3 text-[14px] text-text-primary focus:border-brand-500 focus:outline-none"
        />

        {isLoading && (
          <div role="status" aria-label="Loading persons">
            <SkeletonTable rows={8} />
          </div>
        )}
        {isError && (
          <p role="alert" className="text-[14px] text-error">
            Failed to load persons.
          </p>
        )}

        {!isLoading && !isError && persons.length === 0 && (
          <EmptyState
            icon={Users}
            title="No persons found."
            description={search ? 'No persons match your search.' : 'Use the enrolment wizard to add the first person.'}
            action={
              !search ? (
                <button
                  type="button"
                  onClick={() => setShowEnrol(true)}
                  className="inline-flex items-center gap-1.5 h-9 rounded-[10px] bg-action-700 px-4 text-[13px] font-medium text-white hover:bg-action-800"
                >
                  <Plus className="h-4 w-4" aria-hidden="true" />
                  Enrol Person
                </button>
              ) : undefined
            }
          />
        )}

        {!isLoading && !isError && persons.length > 0 && (
          <div className="rounded-xl border border-border overflow-hidden">
            <table className="w-full text-[14px]">
              <thead className="bg-surface-sunken border-b border-border">
                <tr>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Name
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Employee ID
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
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
                      <span className="flex-1 text-[14px] font-medium text-text-primary">{p.name}</span>
                      <span className="w-36 font-mono text-[13px] text-text-secondary">{p.employee_id}</span>
                      <span className="w-24">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${
                            p.is_active
                              ? 'bg-success/10 text-success'
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
                        className="rounded-[10px] px-3 py-1 text-[13px] text-error hover:bg-error/10 transition-colors"
                      >
                        Delete
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
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
