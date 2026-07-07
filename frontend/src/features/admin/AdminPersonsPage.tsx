import { useState, useMemo } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type ColumnDef } from '@tanstack/react-table'
import { Icon } from '@/shared/design-system/icons'
import { api } from '@/shared/api/client'
import type { PersonResponse } from '@/shared/api/types'
import { EnrolmentWizard } from './components/EnrolmentWizard'
import { GdprDeleteDialog } from './components/GdprDeleteDialog'
import { EmptyState } from './components/EmptyState'
import { Button } from '@/shared/design-system/components/Button'
import { PageHeader } from '@/shared/design-system/components/PageHeader'
import { SkeletonTable } from '@/shared/design-system/components/Skeleton'
import { DataTable } from '@/shared/design-system/components/DataTable'

type PersonExt = PersonResponse & { role?: string }

export function AdminPersonsPage() {
  const queryClient = useQueryClient()
  const [showEnrol, setShowEnrol] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<PersonExt | null>(null)

  const { data, isLoading, isError } = useQuery<PersonResponse[]>({
    queryKey: ['admin', 'persons'],
    queryFn: () => api.get('/api/persons?limit=500'),
  })

  const persons = data ?? []

  const columns = useMemo<ColumnDef<PersonResponse, unknown>[]>(
    () => [
      {
        accessorKey: 'name',
        header: 'Name',
        cell: ({ getValue }) => (
          <span className="font-medium text-text-primary">{getValue() as string}</span>
        ),
      },
      {
        accessorKey: 'employee_id',
        header: 'Employee ID',
        cell: ({ getValue }) => (
          <span className="font-mono text-[13px] text-text-secondary">{getValue() as string}</span>
        ),
      },
      {
        accessorKey: 'is_active',
        header: 'Status',
        cell: ({ getValue }) => {
          const active = getValue() as boolean
          return (
            <span
              className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${
                active ? 'bg-success/10 text-success' : 'bg-surface-sunken text-text-muted'
              }`}
            >
              {active ? 'Active' : 'Inactive'}
            </span>
          )
        },
      },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row }) => (
          <button
            type="button"
            aria-label={`Delete ${row.original.name}`}
            onClick={() => setDeleteTarget(row.original)}
            className="rounded-[10px] px-3 py-1 text-[13px] text-error hover:bg-error/10 transition-colors"
          >
            Delete
          </button>
        ),
      },
    ],
    [],
  )

  return (
    <>
      <Helmet title="Persons — Admin" />
      <div className="p-6">
        <PageHeader
          title="Persons"
          actions={
            <Button onClick={() => setShowEnrol(true)} icon={<Icon.add className="h-4 w-4" aria-hidden="true" />}>
              Enrol Person
            </Button>
          }
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

        {!isLoading && !isError && (
          <DataTable
            columns={columns}
            data={persons}
            filterPlaceholder="Filter by name or employee ID…"
            pageSize={25}
            emptyContent={
              <EmptyState
                icon={Icon.users}
                title="No persons enrolled"
                description="Use the enrolment wizard to add the first person."
                action={
                  <button
                    type="button"
                    onClick={() => setShowEnrol(true)}
                    className="inline-flex items-center gap-1.5 h-9 rounded-[10px] bg-action-700 px-4 text-[13px] font-medium text-white hover:bg-action-800"
                  >
                    <Icon.add className="h-4 w-4" aria-hidden="true" />
                    Enrol Person
                  </button>
                }
              />
            }
          />
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
