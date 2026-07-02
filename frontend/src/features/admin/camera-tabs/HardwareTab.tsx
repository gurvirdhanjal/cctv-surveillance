import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { ProfileResponse } from '@/shared/api/types'

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
        <h2 className="text-[16px] font-medium text-text-primary">Camera Profile</h2>
        <button
          type="button"
          onClick={() => setShowConfirm(true)}
          className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600"
        >
          Run Profiler
        </button>
      </div>

      {isLoading && (
        <p role="status" aria-label="Loading profile">
          Loading…
        </p>
      )}

      {!isLoading && pd && (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-[14px]">
          <div>
            <dt className="text-[12px] text-text-muted mb-0.5">Resolution</dt>
            <dd className="font-medium text-text-primary">
              {pd.resolution_w && pd.resolution_h
                ? `${pd.resolution_w}×${pd.resolution_h}`
                : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-[12px] text-text-muted mb-0.5">Measured FPS</dt>
            <dd className="font-medium text-text-primary">
              {pd.fps_measured != null ? `${pd.fps_measured} fps` : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-[12px] text-text-muted mb-0.5">Focus Score</dt>
            <dd className="font-medium text-text-primary">
              {pd.focus_score != null ? pd.focus_score.toFixed(2) : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-[12px] text-text-muted mb-0.5">Frame Drop Rate</dt>
            <dd className="font-medium text-text-primary">
              {pd.frame_drop_rate != null ? `${(pd.frame_drop_rate * 100).toFixed(1)}%` : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-[12px] text-text-muted mb-0.5">Suggested Tier</dt>
            <dd className="font-medium text-text-primary">{pd.suggested_tier ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-[12px] text-text-muted mb-0.5">Shutter Suggestion</dt>
            <dd className="font-medium text-text-primary">{pd.shutter_suggestion ?? '—'}</dd>
          </div>
        </dl>
      )}

      {!isLoading && !pd && (
        <p className="text-[14px] text-text-muted">
          No profile data yet. Run the profiler to characterise this camera.
        </p>
      )}

      {showConfirm && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Confirm profiler run"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        >
          <div className="bg-surface-base rounded-lg shadow-lg w-full max-w-sm p-6">
            <p className="text-[15px] font-medium text-text-primary mb-2">Run camera profiler?</p>
            <p className="text-[13px] text-text-secondary mb-4">
              This will briefly interrupt the live stream while the profiler analyses camera
              properties.
            </p>
            {profileMutation.isError && (
              <p role="alert" className="mb-3 text-[13px] text-red-600">
                Profiler failed. Please try again.
              </p>
            )}
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => setShowConfirm(false)}
                disabled={profileMutation.isPending}
                className="px-4 py-2 text-[14px] rounded border border-border text-text-secondary hover:text-text-primary disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => profileMutation.mutate()}
                disabled={profileMutation.isPending}
                className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50"
              >
                {profileMutation.isPending ? 'Running…' : 'Run'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
