import { useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link } from 'react-router-dom'
import { api } from '@/shared/api/client'
import type { CameraResponse, CapabilityTier, CameraFromCredentials } from '@/shared/api/types'

const TIER_COLORS: Record<CapabilityTier, string> = {
  FULL: 'bg-brand-100 text-brand-700',
  MID: 'bg-warning/10 text-warning',
  LOW: 'bg-surface-sunken text-text-secondary',
}

// Manufacturer presets fill in the stream path automatically
const MANUFACTURER_PRESETS: Record<string, string> = {
  generic: '',
  hikvision: 'Streaming/Channels/1',
  dahua: 'cam/realmonitor?channel=1&subtype=0',
  axis: 'axis-media/media.amp',
  hanwha: 'profile1/media.smp',
  uniview: 'unicast/c1/s0/live',
}

const addCameraSchema = z.object({
  name: z.string().min(2, 'At least 2 characters').max(200),
  host: z
    .string()
    .min(1, 'IP address or hostname required')
    .max(253)
    .regex(
      /^(\d{1,3}\.){3}\d{1,3}$|^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$/,
      'Enter a valid IP (192.168.1.100) or hostname',
    ),
  port: z.coerce.number().int().min(1).max(65535),
  username: z.string().min(1, 'Username required').max(200),
  password: z.string().min(1, 'Password required').max(200),
  stream_path: z.string().max(300).optional(),
  capability_tier: z.preprocess(
    (v) => (v === '' ? undefined : v),
    z.enum(['FULL', 'MID', 'LOW']).optional(),
  ),
})

type AddCameraForm = z.infer<typeof addCameraSchema>

export function AdminCamerasPage() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [manufacturer, setManufacturer] = useState('generic')
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)

  const { data: cameras = [], isLoading, isError } = useQuery<CameraResponse[]>({
    queryKey: ['admin', 'cameras'],
    queryFn: () => api.get('/api/cameras'),
  })

  const deleteMutation = useMutation({
    mutationFn: (cameraId: number) => api.delete(`/api/cameras/${cameraId}`),
    onSuccess: () => {
      setConfirmDeleteId(null)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'cameras'] })
    },
  })

  const {
    register,
    handleSubmit,
    reset,
    setValue,
    formState: { errors },
  } = useForm<AddCameraForm>({
    resolver: zodResolver(addCameraSchema),
    defaultValues: { port: 554 },
  })

  const addMutation = useMutation({
    mutationFn: (data: CameraFromCredentials) => api.post('/api/cameras/from-credentials', data),
    onSuccess: () => {
      reset()
      setManufacturer('generic')
      setShowAdd(false)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'cameras'] })
    },
  })

  function onManufacturerChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const key = e.target.value
    setManufacturer(key)
    setValue('stream_path', MANUFACTURER_PRESETS[key] ?? '')
  }

  function onSubmit(data: AddCameraForm) {
    addMutation.mutate({
      name: data.name,
      host: data.host,
      port: data.port,
      username: data.username,
      password: data.password,
      stream_path: data.stream_path ?? '',
      capability_tier: data.capability_tier,
    })
  }

  function closeModal() {
    reset()
    setManufacturer('generic')
    setShowAdd(false)
  }

  return (
    <>
      <Helmet title="Cameras — Admin" />
      <div className="p-6">
        {deleteMutation.isError && (
          <p role="alert" className="mb-3 text-[13px] text-error">
            {(deleteMutation.error as { status?: number })?.status === 409
              ? 'Camera has associated records. Deactivate it instead of deleting.'
              : 'Failed to delete camera. Please try again.'}
          </p>
        )}

        <div className="flex items-center justify-between mb-4">
          <h1 className="text-[22px] font-semibold text-text-primary">Cameras</h1>
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
          >
            Add Camera
          </button>
        </div>

        {isLoading && (
          <div className="space-y-2" role="status" aria-label="Loading cameras">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 animate-pulse rounded border border-border bg-surface-raised" />
            ))}
          </div>
        )}

        {isError && (
          <p role="alert" className="text-[14px] text-error">
            Failed to load cameras. Check that the API server is running.
          </p>
        )}

        {!isLoading && !isError && (
          <div className="rounded border border-border overflow-hidden">
            <table className="w-full text-[14px]">
              <thead className="bg-surface-sunken border-b border-border">
                <tr>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-muted uppercase tracking-wide">
                    Name
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-muted uppercase tracking-wide">
                    Host
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
                    <td className="px-4 py-3 font-mono text-[13px] text-text-secondary">
                      {cam.rtsp_url}
                    </td>
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
                      {confirmDeleteId === cam.camera_id ? (
                        <span className="flex items-center justify-end gap-3">
                          <button
                            type="button"
                            onClick={() => deleteMutation.mutate(cam.camera_id)}
                            disabled={deleteMutation.isPending}
                            className="text-[13px] text-error hover:underline disabled:opacity-50"
                          >
                            {deleteMutation.isPending ? 'Deleting…' : 'Confirm delete'}
                          </button>
                          <button
                            type="button"
                            onClick={() => setConfirmDeleteId(null)}
                            className="text-[13px] text-text-muted hover:text-text-primary"
                          >
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <span className="flex items-center justify-end gap-4">
                          <Link
                            to={`/admin/cameras/${cam.camera_id}`}
                            className="text-brand-500 hover:underline text-[13px]"
                            aria-label={`Configure ${cam.name}`}
                          >
                            Configure
                          </Link>
                          <button
                            type="button"
                            onClick={() => setConfirmDeleteId(cam.camera_id)}
                            className="text-[13px] text-error hover:underline"
                            aria-label={`Delete ${cam.name}`}
                          >
                            Delete
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
                {cameras.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-6 text-center text-[14px] text-text-muted"
                    >
                      No cameras configured. Add your first camera to get started.
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
          <div className="bg-surface-base rounded-lg shadow-lg w-full max-w-lg p-6">
            <h2 className="text-[17px] font-semibold text-text-primary mb-1">Add Camera</h2>
            <p className="text-[13px] text-text-muted mb-5">
              Enter the camera's network address and credentials. The RTSP stream URL is
              assembled securely on the server.
            </p>

            <form aria-label="Add camera form" onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              {/* Camera name */}
              <div>
                <label htmlFor="cam-name" className="block text-[13px] font-medium text-text-secondary mb-1">
                  Camera name
                </label>
                <input
                  id="cam-name"
                  {...register('name')}
                  className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary focus:outline-none focus:border-brand-500 transition-colors"
                  placeholder="Assembly Line 1"
                />
                {errors.name && (
                  <p role="alert" className="mt-1 text-[12px] text-error">{errors.name.message}</p>
                )}
              </div>

              {/* Manufacturer preset */}
              <div>
                <label htmlFor="cam-manufacturer" className="block text-[13px] font-medium text-text-secondary mb-1">
                  Manufacturer
                </label>
                <select
                  id="cam-manufacturer"
                  value={manufacturer}
                  onChange={onManufacturerChange}
                  className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary focus:outline-none focus:border-brand-500 transition-colors"
                >
                  <option value="generic">Generic / ONVIF</option>
                  <option value="hikvision">Hikvision</option>
                  <option value="dahua">Dahua</option>
                  <option value="axis">Axis</option>
                  <option value="hanwha">Hanwha / Samsung</option>
                  <option value="uniview">Uniview</option>
                </select>
              </div>

              {/* IP + Port row */}
              <div className="flex gap-3">
                <div className="flex-1">
                  <label htmlFor="cam-host" className="block text-[13px] font-medium text-text-secondary mb-1">
                    IP address
                  </label>
                  <input
                    id="cam-host"
                    {...register('host')}
                    className="w-full border border-border rounded px-3 py-2 text-[14px] font-mono bg-surface-base text-text-primary focus:outline-none focus:border-brand-500 transition-colors"
                    placeholder="192.168.1.100"
                    autoComplete="off"
                  />
                  {errors.host && (
                    <p role="alert" className="mt-1 text-[12px] text-error">{errors.host.message}</p>
                  )}
                </div>
                <div className="w-24">
                  <label htmlFor="cam-port" className="block text-[13px] font-medium text-text-secondary mb-1">
                    Port
                  </label>
                  <input
                    id="cam-port"
                    type="number"
                    {...register('port')}
                    className="w-full border border-border rounded px-3 py-2 text-[14px] font-mono bg-surface-base text-text-primary focus:outline-none focus:border-brand-500 transition-colors"
                    placeholder="554"
                  />
                  {errors.port && (
                    <p role="alert" className="mt-1 text-[12px] text-error">{errors.port.message}</p>
                  )}
                </div>
              </div>

              {/* Username + Password row */}
              <div className="flex gap-3">
                <div className="flex-1">
                  <label htmlFor="cam-username" className="block text-[13px] font-medium text-text-secondary mb-1">
                    Username
                  </label>
                  <input
                    id="cam-username"
                    {...register('username')}
                    className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary focus:outline-none focus:border-brand-500 transition-colors"
                    placeholder="admin"
                    autoComplete="username"
                  />
                  {errors.username && (
                    <p role="alert" className="mt-1 text-[12px] text-error">{errors.username.message}</p>
                  )}
                </div>
                <div className="flex-1">
                  <label htmlFor="cam-password" className="block text-[13px] font-medium text-text-secondary mb-1">
                    Password
                  </label>
                  <input
                    id="cam-password"
                    type="password"
                    {...register('password')}
                    className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary focus:outline-none focus:border-brand-500 transition-colors"
                    placeholder="••••••••"
                    autoComplete="current-password"
                  />
                  {errors.password && (
                    <p role="alert" className="mt-1 text-[12px] text-error">{errors.password.message}</p>
                  )}
                </div>
              </div>

              {/* Stream path */}
              <div>
                <label htmlFor="cam-path" className="block text-[13px] font-medium text-text-secondary mb-1">
                  Stream path
                  <span className="ml-1 text-text-muted font-normal">(auto-filled from manufacturer)</span>
                </label>
                <input
                  id="cam-path"
                  {...register('stream_path')}
                  className="w-full border border-border rounded px-3 py-2 text-[14px] font-mono bg-surface-base text-text-primary focus:outline-none focus:border-brand-500 transition-colors"
                  placeholder="Streaming/Channels/1"
                />
              </div>

              {/* Capability tier */}
              <div>
                <label htmlFor="cam-tier" className="block text-[13px] font-medium text-text-secondary mb-1">
                  Capability tier
                </label>
                <select
                  id="cam-tier"
                  {...register('capability_tier')}
                  className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary focus:outline-none focus:border-brand-500 transition-colors"
                >
                  <option value="">Auto-detect</option>
                  <option value="FULL">FULL — face + body + anomaly</option>
                  <option value="MID">MID — face + body only</option>
                  <option value="LOW">LOW — body only</option>
                </select>
              </div>

              {addMutation.isError && (
                <p role="alert" className="text-[13px] text-error">
                  Failed to add camera. Check the IP address and credentials.
                </p>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={closeModal}
                  className="px-4 py-2 text-[14px] rounded border border-border text-text-secondary hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addMutation.isPending}
                  className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-700 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
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
