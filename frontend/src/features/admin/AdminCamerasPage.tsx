import { useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link } from 'react-router-dom'
import { api } from '@/shared/api/client'
import type { CameraResponse, CapabilityTier, CameraCreate } from '@/shared/api/types'

const TIER_COLORS: Record<CapabilityTier, string> = {
  FULL: 'bg-brand-100 text-brand-700',
  MID: 'bg-yellow-100 text-yellow-800',
  LOW: 'bg-surface-sunken text-text-secondary',
}

const addCameraSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters').max(200),
  rtsp_url: z
    .string()
    .min(5, 'URL required')
    .regex(/^(rtsp|rtsps|http|https):\/\/.+/, 'Must be a valid RTSP or HTTP URL'),
  capability_tier: z.preprocess(
    (v) => (v === '' ? undefined : v),
    z.enum(['FULL', 'MID', 'LOW']).optional(),
  ),
  shutter_type: z.preprocess(
    (v) => (v === '' ? undefined : v),
    z.enum(['rolling', 'global', 'unknown']).optional(),
  ),
})

type AddCameraForm = z.infer<typeof addCameraSchema>

export function AdminCamerasPage() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)

  const { data: cameras = [], isLoading } = useQuery<CameraResponse[]>({
    queryKey: ['admin', 'cameras'],
    queryFn: () => api.get('/api/cameras'),
  })

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AddCameraForm>({ resolver: zodResolver(addCameraSchema) })

  const addMutation = useMutation({
    mutationFn: (data: CameraCreate) => api.post('/api/cameras', data),
    onSuccess: () => {
      reset()
      setShowAdd(false)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'cameras'] })
    },
  })

  function onSubmit(data: AddCameraForm) {
    addMutation.mutate(data)
  }

  return (
    <>
      <Helmet title="Cameras — Admin" />
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-[22px] font-semibold text-text-primary">Cameras</h1>
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600"
          >
            Add Camera
          </button>
        </div>

        {isLoading && (
          <p role="status" aria-label="Loading cameras">
            Loading…
          </p>
        )}

        {!isLoading && (
          <div className="rounded border border-border overflow-hidden">
            <table className="w-full text-[14px]">
              <thead className="bg-surface-sunken border-b border-border">
                <tr>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-muted uppercase tracking-wide">
                    Name
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-muted uppercase tracking-wide">
                    Tier
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-muted uppercase tracking-wide">
                    Status
                  </th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {cameras.map((cam) => (
                  <tr key={cam.camera_id} className="hover:bg-surface-raised">
                    <td className="px-4 py-3 font-medium text-text-primary">{cam.name}</td>
                    <td className="px-4 py-3">
                      <span
                        data-testid={`tier-badge-${cam.camera_id}`}
                        className={`inline-block px-2 py-0.5 rounded text-[11px] font-medium ${
                          TIER_COLORS[cam.capability_tier as CapabilityTier] ?? TIER_COLORS.LOW
                        }`}
                      >
                        {cam.capability_tier}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-text-secondary">
                      {cam.is_active ? 'Active' : 'Inactive'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        to={`/admin/cameras/${cam.camera_id}`}
                        className="text-brand-600 hover:underline text-[13px]"
                        aria-label={`Configure ${cam.name}`}
                      >
                        Configure
                      </Link>
                    </td>
                  </tr>
                ))}
                {cameras.length === 0 && (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-6 text-center text-[14px] text-text-muted"
                    >
                      No cameras configured.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showAdd && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Add camera"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        >
          <div className="bg-surface-base rounded-lg shadow-lg w-full max-w-md p-6">
            <h2 className="text-[17px] font-semibold text-text-primary mb-4">Add Camera</h2>
            <form
              aria-label="Add camera form"
              onSubmit={handleSubmit(onSubmit)}
              className="space-y-4"
            >
              <div>
                <label
                  htmlFor="cam-name"
                  className="block text-[13px] font-medium text-text-secondary mb-1"
                >
                  Camera name
                </label>
                <input
                  id="cam-name"
                  {...register('name')}
                  className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="Assembly Line 1"
                />
                {errors.name && (
                  <p role="alert" className="mt-1 text-[12px] text-red-600">
                    {errors.name.message}
                  </p>
                )}
              </div>
              <div>
                <label
                  htmlFor="cam-rtsp"
                  className="block text-[13px] font-medium text-text-secondary mb-1"
                >
                  RTSP URL
                </label>
                <input
                  id="cam-rtsp"
                  {...register('rtsp_url')}
                  className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary font-mono focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="rtsp://camera/stream"
                />
                {errors.rtsp_url && (
                  <p role="alert" className="mt-1 text-[12px] text-red-600">
                    {errors.rtsp_url.message}
                  </p>
                )}
              </div>
              <div>
                <label
                  htmlFor="cam-tier"
                  className="block text-[13px] font-medium text-text-secondary mb-1"
                >
                  Capability tier
                </label>
                <select
                  id="cam-tier"
                  {...register('capability_tier')}
                  className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-500"
                >
                  <option value="">Auto-detect</option>
                  <option value="FULL">FULL</option>
                  <option value="MID">MID</option>
                  <option value="LOW">LOW</option>
                </select>
              </div>
              {addMutation.isError && (
                <p role="alert" className="text-[13px] text-red-600">
                  Failed to add camera.
                </p>
              )}
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    reset()
                    setShowAdd(false)
                  }}
                  className="px-4 py-2 text-[14px] rounded border border-border text-text-secondary hover:text-text-primary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addMutation.isPending}
                  className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50"
                >
                  {addMutation.isPending ? 'Adding…' : 'Add Camera'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
