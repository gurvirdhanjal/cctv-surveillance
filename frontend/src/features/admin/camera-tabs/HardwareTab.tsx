import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Cpu } from 'lucide-react'
import { api } from '@/shared/api/client'
import type { ProfileResponse } from '@/shared/api/types'
import { EmptyState } from '../components/EmptyState'
import { Skeleton, SkeletonText } from '@/shared/design-system/components/Skeleton'
import { Button } from '@/shared/design-system/components/Button'

interface Props {
  cameraId: number
}

export function HardwareTab({ cameraId }: Props) {
  const queryClient = useQueryClient()
  const [showConfirm, setShowConfirm] = useState(false)

  const { data: profile, isLoading } = useQuery<ProfileResponse>({
    queryKey: ['admin', 'cameras', cameraId, 'profile'],
    queryFn: () => api.get(`/api/cameras/${cameraId}/profile`),
  })

  const profileMutation = useMutation({
    mutationFn: () => api.post(`/api/cameras/${cameraId}/profile`, {}),
    onSuccess: () => {
      setShowConfirm(false)
      void queryClient.invalidateQueries({
        queryKey: ['admin', 'cameras', cameraId, 'profile'],
      })
    },
  })

  const pd = profile?.profile_data

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
          Camera Profile
        </h2>
        <Button
          type="button"
          size="sm"
          onClick={() => setShowConfirm(true)}
        >
          <Cpu className="h-4 w-4" aria-hidden="true" />
          Run Profiler
        </Button>
      </div>

      {isLoading && (
        <div role="status" aria-label="Loading profile">
          <div className="space-y-4">
            <Skeleton className="h-48 w-full" />
            <SkeletonText lines={4} />
          </div>
        </div>
      )}

      {!isLoading && !pd && (
        <EmptyState
          icon={Cpu}
          title="No profile data yet"
          description="Run the profiler to characterise this camera's hardware properties."
          cta={<span className="text-xs text-text-muted">Run the camera profiler to populate this section</span>}
        />
      )}

      {!isLoading && pd && (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 rounded-xl border border-border bg-surface-base p-5 text-[14px]">
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted mb-1">
              Resolution
            </dt>
            <dd className="font-medium text-text-primary">
              {pd.resolution_w && pd.resolution_h
                ? `${pd.resolution_w}×${pd.resolution_h}`
                : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted mb-1">
              Measured FPS
            </dt>
            <dd className="font-medium text-text-primary">
              {pd.fps_measured != null ? `${pd.fps_measured} fps` : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted mb-1">
              Focus Score
            </dt>
            <dd className="font-medium text-text-primary">
              {pd.focus_score != null ? pd.focus_score.toFixed(2) : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted mb-1">
              Frame Drop Rate
            </dt>
            <dd className="font-medium text-text-primary">
              {pd.frame_drop_rate != null ? `${(pd.frame_drop_rate * 100).toFixed(1)}%` : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted mb-1">
              Suggested Tier
            </dt>
            <dd className="font-medium text-text-primary">{pd.suggested_tier ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted mb-1">
              Shutter Suggestion
            </dt>
            <dd className="font-medium text-text-primary">{pd.shutter_suggestion ?? '—'}</dd>
          </div>
        </dl>
      )}

      {showConfirm && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Confirm profiler run"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        >
          <div className="w-full max-w-sm rounded-xl bg-surface-base p-6 shadow-lg">
            <p className="mb-2 text-[15px] font-semibold text-text-primary">Run camera profiler?</p>
            <p className="mb-4 text-[13px] text-text-secondary">
              This will briefly interrupt the live stream while the profiler analyses camera
              properties.
            </p>
            {profileMutation.isError && (
              <p role="alert" className="mb-3 text-[13px] text-error">
                Profiler failed. Please try again.
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => setShowConfirm(false)}
                disabled={profileMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={() => profileMutation.mutate()}
                disabled={profileMutation.isPending}
                loading={profileMutation.isPending}
              >
                {profileMutation.isPending ? 'Running…' : 'Run'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
