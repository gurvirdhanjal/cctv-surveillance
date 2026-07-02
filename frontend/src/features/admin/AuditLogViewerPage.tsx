import { useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { AuditLogEntry, AuditVerifyResponse } from '@/shared/api/types'

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
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-[22px] font-semibold text-text-primary">Audit Log</h1>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => verifyMutation.mutate()}
              disabled={verifyMutation.isPending}
              className="px-4 py-2 text-[14px] rounded border border-border-subtle text-text-secondary hover:text-text-primary disabled:opacity-50"
            >
              {verifyMutation.isPending ? 'Verifying…' : 'Verify Chain'}
            </button>
            <button
              type="button"
              onClick={handleExport}
              aria-label="Export audit log PDF"
              className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600"
            >
              Export PDF
            </button>
          </div>
        </div>

        {verifyResult && (
          <div
            role="status"
            aria-label="Chain verification result"
            className={`mb-4 rounded border p-3 text-[13px] ${
              verifyResult.broken_chain_at
                ? 'bg-red-50 border-red-200 text-red-800'
                : 'bg-green-50 border-green-200 text-green-800'
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
          <p role="alert" className="mb-4 text-[13px] text-red-600">
            {verifyError}
          </p>
        )}

        {isLoading && (
          <p role="status" aria-label="Loading audit log">
            Loading…
          </p>
        )}

        {!isLoading && (
          <div className="rounded border border-border-subtle overflow-hidden">
            <table className="w-full text-[13px]">
              <thead className="bg-surface-sunken border-b border-border-subtle">
                <tr>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-tertiary uppercase">
                    ID
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-tertiary uppercase">
                    Timestamp
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-tertiary uppercase">
                    Event
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-tertiary uppercase">
                    Actor
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-tertiary uppercase">
                    Subject
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-tertiary uppercase">
                    Hash
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {entries.map((e) => (
                  <tr key={e.log_id} className="hover:bg-surface-hover">
                    <td className="px-4 py-2 font-mono text-text-tertiary">{e.log_id}</td>
                    <td className="px-4 py-2 font-mono text-text-secondary">
                      {e.created_at.slice(0, 19).replace('T', ' ')}
                    </td>
                    <td className="px-4 py-2 font-medium text-text-primary">{e.event_type}</td>
                    <td className="px-4 py-2 text-text-secondary">
                      {e.actor_role ? `${e.actor_role}#${e.actor_user_id ?? '?'}` : '—'}
                    </td>
                    <td className="px-4 py-2 text-text-secondary font-mono text-[12px]">
                      {e.subject_table ? `${e.subject_table}/${e.subject_id}` : '—'}
                    </td>
                    <td className="px-4 py-2 font-mono text-[11px] text-text-tertiary max-w-[80px] truncate">
                      {e.row_hash.slice(0, 8)}…
                    </td>
                  </tr>
                ))}
                {entries.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-6 text-center text-[14px] text-text-tertiary"
                    >
                      No audit entries found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
