import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { AnomalyDetector } from '@/shared/api/types'

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
        <h1 className="text-[22px] font-semibold text-text-primary mb-4">Anomaly Detectors</h1>

        {isLoading && (
          <p role="status" aria-label="Loading detectors">
            Loading…
          </p>
        )}

        {!isLoading && (
          <div className="rounded border border-border-subtle overflow-hidden">
            <table className="w-full text-[14px]">
              <thead className="bg-surface-sunken border-b border-border-subtle">
                <tr>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-tertiary uppercase">
                    Alert Type
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-tertiary uppercase">
                    Class
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-tertiary uppercase">
                    Model Version
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-tertiary uppercase">
                    Enabled
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {detectors.map((d) => (
                  <tr key={d.detector_id} className="hover:bg-surface-hover">
                    <td className="px-4 py-3 font-medium text-text-primary">{d.alert_type}</td>
                    <td className="px-4 py-3 font-mono text-[12px] text-text-secondary">
                      {d.class_path.split('.').pop()}
                    </td>
                    <td className="px-4 py-3 text-text-secondary font-mono text-[12px]">
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
                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1 disabled:opacity-50 ${
                          d.is_enabled ? 'bg-brand-500' : 'bg-surface-sunken border border-border-subtle'
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
                {detectors.length === 0 && (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-6 text-center text-[14px] text-text-tertiary"
                    >
                      No anomaly detectors configured.
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
