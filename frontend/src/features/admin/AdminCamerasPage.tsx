import { useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Link } from 'react-router-dom'
import { Camera as CameraIcon } from 'lucide-react'
import { Icon } from '@/shared/design-system/icons'
import { api } from '@/shared/api/client'
import { useAuthStore } from '@/stores/authStore'
import type {
  CameraResponse,
  CapabilityTier,
  CameraFromCredentials,
  ProfileData,
} from '@/shared/api/types'
import { Button } from '@/shared/design-system/components/Button'
import { ActionBar } from '@/shared/design-system/components/ActionBar'

const TIER_COLORS: Record<CapabilityTier, string> = {
  FULL: 'bg-brand-100 text-brand-700',
  MID: 'bg-warning/10 text-warning',
  LOW: 'bg-surface-sunken text-text-secondary',
}

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

function parseProfile(raw: string | null): ProfileData | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as ProfileData
  } catch {
    return null
  }
}

function CameraStatusBadge({
  cam,
}: {
  cam: CameraResponse
}) {
  if (cam.recalibrate_required_at) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-warning/85 px-2 py-0.5 text-[11px] font-semibold text-white backdrop-blur-sm">
        <span className="h-1.5 w-1.5 rounded-full bg-white/80" />
        Calibration
      </span>
    )
  }
  if (cam.is_active) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-success/85 px-2 py-0.5 text-[11px] font-semibold text-white backdrop-blur-sm">
        <span className="h-1.5 w-1.5 animate-status-pulse rounded-full bg-white" />
        Online
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-black/55 px-2 py-0.5 text-[11px] font-semibold text-white/70 backdrop-blur-sm">
      <span className="h-1.5 w-1.5 rounded-full bg-white/40" />
      Offline
    </span>
  )
}

export function AdminCamerasPage() {
  const queryClient = useQueryClient()
  const token = useAuthStore((s) => s.token)
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
          <p role="alert" className="mb-4 text-[13px] text-error">
            {(deleteMutation.error as { status?: number })?.status === 409
              ? 'Camera has associated records. Deactivate it instead of deleting.'
              : 'Failed to delete camera. Please try again.'}
          </p>
        )}

        <ActionBar
          aria-label="Camera page actions"
          left={<h1 className="text-[22px] font-bold leading-tight text-text-primary">Cameras</h1>}
          right={
            <Button onClick={() => setShowAdd(true)} icon={<Icon.add className="h-4 w-4" aria-hidden="true" />}>
              Add Camera
            </Button>
          }
          className="mb-6 rounded-xl"
        />

        {isLoading && (
          <div
            className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3"
            role="status"
            aria-label="Loading cameras"
          >
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="overflow-hidden rounded-xl border border-border bg-surface-base animate-pulse"
              >
                <div className="aspect-video bg-surface-sunken" />
                <div className="p-5 space-y-3">
                  <div className="h-4 w-2/3 rounded-lg bg-surface-sunken" />
                  <div className="h-3 w-1/3 rounded-lg bg-surface-sunken" />
                  <div className="flex gap-2 pt-1">
                    <div className="h-8 w-16 rounded-lg bg-surface-sunken" />
                    <div className="h-8 w-16 rounded-lg bg-surface-sunken" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {isError && (
          <p role="alert" className="text-[14px] text-error">
            Failed to load cameras. Check that the API server is running.
          </p>
        )}

        {!isLoading && !isError && cameras.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface-base py-20 text-center">
            <CameraIcon className="mb-4 h-10 w-10 text-text-muted opacity-30" aria-hidden="true" />
            <p className="text-[15px] font-semibold text-text-secondary">No cameras configured</p>
            <p className="mt-1 text-[13px] text-text-muted">
              Add your first camera to get started.
            </p>
          </div>
        )}

        {!isLoading && !isError && cameras.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {cameras.map((cam) => {
              const profile = parseProfile(cam.profile_data)
              return (
                <div
                  key={cam.camera_id}
                  className="overflow-hidden rounded-xl border border-border bg-surface-base transition-shadow hover:shadow-[var(--shadow-2)]"
                >
                  {/* Snapshot thumbnail */}
                  <div className="relative aspect-video bg-surface-sunken">
                    {token && (
                      <img
                        className="absolute inset-0 h-full w-full object-cover"
                        src={`/api/cameras/${cam.camera_id}/snapshot?token=${encodeURIComponent(token)}`}
                        alt={`${cam.name} snapshot`}
                        loading="lazy"
                        onError={(e) => {
                          ;(e.currentTarget as HTMLImageElement).style.display = 'none'
                        }}
                      />
                    )}
                    {/* Placeholder icon — shown when no token or img errors */}
                    <div className="absolute inset-0 flex items-center justify-center">
                      <CameraIcon className="h-8 w-8 text-text-muted opacity-20" aria-hidden="true" />
                    </div>
                    <span className="absolute left-2 top-2">
                      <CameraStatusBadge cam={cam} />
                    </span>
                    {/* Profile metadata overlay */}
                    {profile && (
                      <div className="absolute bottom-2 right-2 flex items-center gap-1.5 rounded-lg bg-black/60 px-2 py-1 text-[11px] font-medium text-white backdrop-blur-sm">
                        {profile.fps_measured != null && (
                          <span>{Math.round(profile.fps_measured)}fps</span>
                        )}
                        {profile.resolution_w != null && profile.resolution_h != null && (
                          <>
                            {profile.fps_measured != null && <span className="text-white/40">·</span>}
                            <span>{profile.resolution_w}×{profile.resolution_h}</span>
                          </>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Card body */}
                  <div className="p-5">
                    <div className="mb-3 flex items-start justify-between gap-2">
                      <p className="text-[14px] font-semibold leading-snug text-text-primary">
                        {cam.name}
                      </p>
                      <span
                        data-testid={`tier-badge-${cam.camera_id}`}
                        className={`shrink-0 inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          TIER_COLORS[cam.capability_tier as CapabilityTier] ?? TIER_COLORS.LOW
                        }`}
                      >
                        {cam.capability_tier}
                      </span>
                    </div>

                    {/* AI capability indicator */}
                    <p className="mb-4 text-[12px] text-text-muted">
                      {cam.capability_tier === 'FULL'
                        ? 'Face · Body · Anomaly'
                        : cam.capability_tier === 'MID'
                          ? 'Face · Body'
                          : 'Body only'}
                    </p>

                    {confirmDeleteId === cam.camera_id ? (
                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={() => deleteMutation.mutate(cam.camera_id)}
                          disabled={deleteMutation.isPending}
                          className="text-[13px] font-medium text-error hover:underline disabled:opacity-50"
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
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        <Link
                          to="/live"
                          className="inline-flex items-center gap-1.5 rounded-[10px] bg-action-700 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-action-800 transition-colors"
                        >
                          <Icon.live className="h-3.5 w-3.5" aria-hidden="true" />
                          Live
                        </Link>
                        <Link
                          to={`/admin/cameras/${cam.camera_id}`}
                          className="inline-flex items-center gap-1.5 rounded-[10px] border border-border px-3 py-1.5 text-[12px] font-medium text-text-secondary hover:border-brand-500/40 hover:text-text-primary transition-colors"
                          aria-label={`Settings ${cam.name}`}
                        >
                          <Icon.settings className="h-3.5 w-3.5" aria-hidden="true" />
                          Settings
                        </Link>
                        <button
                          type="button"
                          onClick={() => setConfirmDeleteId(cam.camera_id)}
                          className="ml-auto rounded-[10px] p-1.5 text-text-muted hover:bg-error/10 hover:text-error transition-colors"
                          aria-label={`Delete ${cam.name}`}
                        >
                          <Icon.delete className="h-4 w-4" aria-hidden="true" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* ── Add camera modal ─────────────────────────────────────────────── */}
      {showAdd && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Add camera"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        >
          <div className="w-full max-w-lg rounded-xl bg-surface-base p-6 shadow-lg">
            <h2 className="mb-1 text-[17px] font-semibold text-text-primary">Add Camera</h2>
            <p className="mb-5 text-[13px] text-text-muted">
              Enter the camera's network address and credentials. The RTSP stream URL is
              assembled securely on the server.
            </p>

            <form aria-label="Add camera form" onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <div>
                <label htmlFor="cam-name" className="mb-1 block text-[13px] font-medium text-text-secondary">
                  Camera name
                </label>
                <input
                  id="cam-name"
                  {...register('name')}
                  className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] text-text-primary transition-colors focus:border-brand-500 focus:outline-none"
                  placeholder="Assembly Line 1"
                />
                {errors.name && (
                  <p role="alert" className="mt-1 text-[12px] text-error">{errors.name.message}</p>
                )}
              </div>

              <div>
                <label htmlFor="cam-manufacturer" className="mb-1 block text-[13px] font-medium text-text-secondary">
                  Manufacturer
                </label>
                <select
                  id="cam-manufacturer"
                  value={manufacturer}
                  onChange={onManufacturerChange}
                  className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] text-text-primary transition-colors focus:border-brand-500 focus:outline-none"
                >
                  <option value="generic">Generic / ONVIF</option>
                  <option value="hikvision">Hikvision</option>
                  <option value="dahua">Dahua</option>
                  <option value="axis">Axis</option>
                  <option value="hanwha">Hanwha / Samsung</option>
                  <option value="uniview">Uniview</option>
                </select>
              </div>

              <div className="flex gap-3">
                <div className="flex-1">
                  <label htmlFor="cam-host" className="mb-1 block text-[13px] font-medium text-text-secondary">
                    IP address
                  </label>
                  <input
                    id="cam-host"
                    {...register('host')}
                    className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] font-mono text-text-primary transition-colors focus:border-brand-500 focus:outline-none"
                    placeholder="192.168.1.100"
                    autoComplete="off"
                  />
                  {errors.host && (
                    <p role="alert" className="mt-1 text-[12px] text-error">{errors.host.message}</p>
                  )}
                </div>
                <div className="w-24">
                  <label htmlFor="cam-port" className="mb-1 block text-[13px] font-medium text-text-secondary">
                    Port
                  </label>
                  <input
                    id="cam-port"
                    type="number"
                    {...register('port')}
                    className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] font-mono text-text-primary transition-colors focus:border-brand-500 focus:outline-none"
                    placeholder="554"
                  />
                  {errors.port && (
                    <p role="alert" className="mt-1 text-[12px] text-error">{errors.port.message}</p>
                  )}
                </div>
              </div>

              <div className="flex gap-3">
                <div className="flex-1">
                  <label htmlFor="cam-username" className="mb-1 block text-[13px] font-medium text-text-secondary">
                    Username
                  </label>
                  <input
                    id="cam-username"
                    {...register('username')}
                    className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] text-text-primary transition-colors focus:border-brand-500 focus:outline-none"
                    placeholder="admin"
                    autoComplete="username"
                  />
                  {errors.username && (
                    <p role="alert" className="mt-1 text-[12px] text-error">{errors.username.message}</p>
                  )}
                </div>
                <div className="flex-1">
                  <label htmlFor="cam-password" className="mb-1 block text-[13px] font-medium text-text-secondary">
                    Password
                  </label>
                  <input
                    id="cam-password"
                    type="password"
                    {...register('password')}
                    className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] text-text-primary transition-colors focus:border-brand-500 focus:outline-none"
                    placeholder="••••••••"
                    autoComplete="current-password"
                  />
                  {errors.password && (
                    <p role="alert" className="mt-1 text-[12px] text-error">{errors.password.message}</p>
                  )}
                </div>
              </div>

              <div>
                <label htmlFor="cam-path" className="mb-1 block text-[13px] font-medium text-text-secondary">
                  Stream path
                  <span className="ml-1 font-normal text-text-muted">(auto-filled from manufacturer)</span>
                </label>
                <input
                  id="cam-path"
                  {...register('stream_path')}
                  className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] font-mono text-text-primary transition-colors focus:border-brand-500 focus:outline-none"
                  placeholder="Streaming/Channels/1"
                />
              </div>

              <div>
                <label htmlFor="cam-tier" className="mb-1 block text-[13px] font-medium text-text-secondary">
                  Capability tier
                </label>
                <select
                  id="cam-tier"
                  {...register('capability_tier')}
                  className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] text-text-primary transition-colors focus:border-brand-500 focus:outline-none"
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
                  className="h-10 rounded-[10px] border border-border px-4 text-[13px] text-text-secondary hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addMutation.isPending}
                  className="h-10 rounded-[10px] bg-action-700 px-4 text-[13px] font-medium text-white hover:bg-action-800 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
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
