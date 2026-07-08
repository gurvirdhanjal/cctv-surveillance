import { useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation } from '@tanstack/react-query'
import { type ColumnDef } from '@tanstack/react-table'
import { ShieldCheck } from 'lucide-react'
import { Icon } from '@/shared/design-system/icons'
import { api } from '@/shared/api/client'
import type { AuditLogEntry, AuditVerifyResponse } from '@/shared/api/types'
import { EmptyState } from './components/EmptyState'
import { Button } from '@/shared/design-system/components/Button'
import { PageHeader } from '@/shared/design-system/components/PageHeader'
import { SkeletonTable } from '@/shared/design-system/components/Skeleton'
import { DataTable } from '@/shared/design-system/components/DataTable'

const AUDIT_COLUMNS: ColumnDef<AuditLogEntry, unknown>[] = [
  {
    accessorKey: 'log_id',
    header: 'ID',
    cell: ({ getValue }) => (
      <span className="font-mono text-text-muted">{getValue() as number}</span>
    ),
  },
  {
    accessorKey: 'created_at',
    header: 'Timestamp',
    cell: ({ getValue }) => (
      <span className="font-mono text-[12px] text-text-secondary">
        {(getValue() as string).slice(0, 19).replace('T', ' ')}
      </span>
    ),
  },
  {
    accessorKey: 'event_type',
    header: 'Event',
    cell: ({ getValue }) => (
      <span className="font-medium text-text-primary">{getValue() as string}</span>
    ),
  },
  {
    id: 'actor',
    header: 'Actor',
    accessorFn: (row) => (row.actor_role ? `${row.actor_role}#${row.actor_user_id ?? '?'}` : '—'),
    cell: ({ getValue }) => (
      <span className="text-[13px] text-text-secondary">{getValue() as string}</span>
    ),
  },
  {
    id: 'subject',
    header: 'Subject',
    accessorFn: (row) => (row.subject_table ? `${row.subject_table}/${row.subject_id}` : '—'),
    cell: ({ getValue }) => (
      <span className="font-mono text-[12px] text-text-secondary">{getValue() as string}</span>
    ),
  },
  {
    accessorKey: 'row_hash',
    header: 'Hash',
    enableSorting: false,
    cell: ({ getValue }) => (
      <span className="font-mono text-[11px] text-text-muted">
        {(getValue() as string).slice(0, 8)}…
      </span>
    ),
  },
]

function AuditTable({ entries }: { entries: AuditLogEntry[] }) {
  return (
    <DataTable
      tableId="audit-log"
      columns={AUDIT_COLUMNS}
      data={entries}
      filterPlaceholder="Filter by event type or actor…"
      pageSize={25}
    />
  )
}

export function AuditLogViewerPage() {
  const [verifyResult, setVerifyResult] = useState<AuditVerifyResponse | null>(null)
  const [verifyError, setVerifyError] = useState<string | null>(null)

  const { data: entries = [], isLoading } = useQuery<AuditLogEntry[]>({
    queryKey: ['admin', 'audit'],
    queryFn: () => api.get('/api/audit?limit=100'),
  })

  const verifyMutation = useMutation({
    mutationFn: (): Promise<AuditVerifyResponse> => api.get('/api/audit/verify'),
    onSuccess: (result) => {
      setVerifyResult(result)
      setVerifyError(null)
    },
    onError: () => {
      setVerifyError('Verification failed. Check backend logs.')
      setVerifyResult(null)
    },
  })

  function handleExport() {
    window.open('/api/audit/export', '_blank', 'noopener,noreferrer')
  }

  return (
    <>
      <Helmet title="Audit Log — Admin" />
      <div className="p-6">
        <PageHeader
          title="Audit Log"
          actions={
            <>
              <Button
                variant="secondary"
                onClick={() => verifyMutation.mutate()}
                disabled={verifyMutation.isPending}
                loading={verifyMutation.isPending}
                icon={<ShieldCheck className="h-4 w-4" aria-hidden="true" />}
              >
                {verifyMutation.isPending ? 'Verifying…' : 'Verify Chain'}
              </Button>
              <Button
                onClick={handleExport}
                aria-label="Export audit log PDF"
                icon={<Icon.export className="h-4 w-4" aria-hidden="true" />}
              >
                Export PDF
              </Button>
            </>
          }
        />

        {verifyResult && (
          <div
            role="status"
            aria-label="Chain verification result"
            className={`mb-4 rounded-xl border p-4 text-[13px] ${
              verifyResult.broken_chain_at
                ? 'bg-error/10 border-error/20 text-error'
                : 'bg-success/10 border-success/20 text-success'
            }`}
          >
            {verifyResult.broken_chain_at ? (
              <>
                Chain broken at log_id <strong>{verifyResult.broken_chain_at}</strong>.{' '}
                {verifyResult.rows_checked} rows checked.
              </>
            ) : (
              <>
                Chain intact — {verifyResult.rows_checked} rows verified. No tampering detected.
              </>
            )}
          </div>
        )}

        {verifyError && (
          <p role="alert" className="mb-4 text-[13px] text-error">
            {verifyError}
          </p>
        )}

        {isLoading && (
          <div role="status" aria-label="Loading audit log">
            <SkeletonTable rows={10} />
          </div>
        )}

        {!isLoading && entries.length === 0 && (
          <EmptyState
            icon={Icon.audit}
            title="No audit entries found."
            description="Events appear here as the system processes requests and state changes."
            cta={<span className="text-xs text-text-muted">Events are recorded automatically</span>}
          />
        )}

        {!isLoading && entries.length > 0 && (
          <AuditTable entries={entries} />
        )}
      </div>
    </>
  )
}
