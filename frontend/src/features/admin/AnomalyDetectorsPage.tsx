import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Zap } from 'lucide-react'
import { api } from '@/shared/api/client'
import type { AnomalyDetector } from '@/shared/api/types'
import { EmptyState } from './components/EmptyState'

export function AnomalyDetectorsPage() {
  const queryClient = useQueryClient()

  const { data: detectors = [], isLoading } = useQuery<AnomalyDetector[]>({
    queryKey: ['admin', 'anomaly-detectors'],
    queryFn: () => api.get('/api/anomaly-detectors'),
  })

  const toggleMutation = useMutation({
    mutationFn: ({ detectorId, enabled }: { detectorId: number; enabled: boolean }) =>
      api.patch(`/api/anomaly-detectors/${detectorId}`, { is_enabled: enabled }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'anomaly-detectors'] })
    },
  })

  return (
    <>
      <Helmet title="Anomaly Detectors — Admin" />
      <div className="p-6">
        <h1 className="mb-5 text-[22px] font-bold text-text-primary">Anomaly Detectors</h1>

        {toggleMutation.isError && (
          <p role="alert" className="mb-3 text-[13px] text-error">
            Failed to update detector. Please try again.
          </p>
        )}

        {isLoading && (
          <p role="status" aria-label="Loading detectors" className="text-[14px] text-text-muted">
            Loading…
          </p>
        )}

        {!isLoading && detectors.length === 0 && (
          <EmptyState
            icon={Zap}
            title="No anomaly detectors configured"
            description="Detectors are registered by the backend on startup. Check the server configuration."
          />
        )}

        {!isLoading && detectors.length > 0 && (
          <div className="rounded-xl border border-border overflow-hidden">
            <table className="w-full text-[14px]">
              <thead className="bg-surface-sunken border-b border-border">
                <tr>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Alert Type
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Class
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Model Version
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Enabled
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {detectors.map((d) => (
                  <tr key={d.detector_id} className="hover:bg-surface-raised">
                    <td className="px-4 py-3 font-medium text-text-primary">{d.alert_type}</td>
                    <td className="px-4 py-3 font-mono text-[12px] text-text-secondary">
                      {d.class_path.split('.').pop()}
                    </td>
                    <td className="px-4 py-3 font-mono text-[12px] text-text-secondary">
                      {d.model_version ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        role="switch"
                        aria-checked={d.is_enabled}
                        aria-label={`${d.is_enabled ? 'Disable' : 'Enable'} ${d.alert_type}`}
                        onClick={() =>
                          toggleMutation.mutate({
                            detectorId: d.detector_id,
                            enabled: !d.is_enabled,
                          })
                        }
                        disabled={toggleMutation.isPending}
                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1 disabled:opacity-50 ${
                          d.is_enabled ? 'bg-brand-500' : 'bg-surface-sunken border border-border'
                        }`}
                      >
                        <span
                          className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                            d.is_enabled ? 'translate-x-4' : 'translate-x-0.5'
                          }`}
                        />
                      </button>
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
