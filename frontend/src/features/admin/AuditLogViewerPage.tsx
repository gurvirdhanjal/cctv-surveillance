import { useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Download, FileText, ShieldCheck } from 'lucide-react'
import { api } from '@/shared/api/client'
import type { AuditLogEntry, AuditVerifyResponse } from '@/shared/api/types'
import { EmptyState } from './components/EmptyState'
import { Button } from '@/shared/design-system/components/Button'
import { PageHeader } from '@/shared/design-system/components/PageHeader'
import { SkeletonTable } from '@/shared/design-system/components/Skeleton'

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
                icon={<Download className="h-4 w-4" aria-hidden="true" />}
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
            icon={FileText}
            title="No audit entries found."
            description="Events appear here as the system processes requests and state changes."
          />
        )}

        {!isLoading && entries.length > 0 && (
          <div className="rounded-xl border border-border overflow-hidden">
            <table className="w-full text-[13px]">
              <thead className="bg-surface-sunken border-b border-border">
                <tr>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    ID
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Timestamp
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Event
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Actor
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Subject
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Hash
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {entries.map((e) => (
                  <tr key={e.log_id} className="hover:bg-surface-raised">
                    <td className="px-4 py-2 font-mono text-text-muted">{e.log_id}</td>
                    <td className="px-4 py-2 font-mono text-text-secondary">
                      {e.created_at.slice(0, 19).replace('T', ' ')}
                    </td>
                    <td className="px-4 py-2 font-medium text-text-primary">{e.event_type}</td>
                    <td className="px-4 py-2 text-text-secondary">
                      {e.actor_role ? `${e.actor_role}#${e.actor_user_id ?? '?'}` : '—'}
                    </td>
                    <td className="px-4 py-2 font-mono text-[12px] text-text-secondary">
                      {e.subject_table ? `${e.subject_table}/${e.subject_id}` : '—'}
                    </td>
                    <td className="px-4 py-2 font-mono text-[11px] text-text-muted max-w-[80px] truncate">
                      {e.row_hash.slice(0, 8)}…
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
