import { useMemo } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { type ColumnDef } from '@tanstack/react-table'
import { Zap } from 'lucide-react'
import { api } from '@/shared/api/client'
import type { AnomalyDetector } from '@/shared/api/types'
import { EmptyState } from './components/EmptyState'
import { SkeletonTable } from '@/shared/design-system/components/Skeleton'
import { PageHeader } from '@/shared/design-system/components/PageHeader'
import { DataTable } from '@/shared/design-system/components/DataTable'
import { Switch } from '@/shared/design-system/components/ui/Switch'

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

  const columns = useMemo<ColumnDef<AnomalyDetector, unknown>[]>(
    () => [
      {
        accessorKey: 'alert_type',
        header: 'Alert Type',
        cell: ({ getValue }) => (
          <span className="font-medium text-text-primary">{getValue() as string}</span>
        ),
      },
      {
        accessorKey: 'class_path',
        header: 'Class',
        cell: ({ getValue }) => (
          <span className="font-mono text-[12px] text-text-secondary">
            {(getValue() as string).split('.').pop()}
          </span>
        ),
      },
      {
        accessorKey: 'model_version',
        header: 'Model Version',
        cell: ({ getValue }) => (
          <span className="font-mono text-[12px] text-text-secondary">
            {(getValue() as string | null) ?? '—'}
          </span>
        ),
      },
      {
        accessorKey: 'is_enabled',
        header: 'Enabled',
        enableSorting: false,
        cell: ({ row }) => (
          <Switch
            checked={row.original.is_enabled}
            onCheckedChange={(checked) =>
              toggleMutation.mutate({ detectorId: row.original.detector_id, enabled: checked })
            }
            disabled={toggleMutation.isPending}
            aria-label={`${row.original.is_enabled ? 'Disable' : 'Enable'} ${row.original.alert_type}`}
          />
        ),
      },
    ],
    [toggleMutation],
  )

  return (
    <>
      <Helmet title="Anomaly Detectors — Admin" />
      <div className="p-6">
        <PageHeader title="Anomaly Detectors" />

        {toggleMutation.isError && (
          <p role="alert" className="mb-3 text-[13px] text-error">
            Failed to update detector. Please try again.
          </p>
        )}

        {isLoading && (
          <div role="status" aria-label="Loading detectors">
            <SkeletonTable rows={6} />
          </div>
        )}

        {!isLoading && detectors.length === 0 && (
          <EmptyState
            icon={Zap}
            title="No anomaly detectors configured"
            description="Detectors are registered by the backend on startup. Check the server configuration."
          />
        )}

        {!isLoading && detectors.length > 0 && (
          <DataTable
            columns={columns}
            data={detectors}
            filterPlaceholder="Filter detectors…"
            pageSize={20}
          />
        )}
      </div>
    </>
  )
}
