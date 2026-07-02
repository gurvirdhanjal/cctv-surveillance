import { useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { parseExpression } from 'cron-parser'
import { api } from '@/shared/api/client'
import type { MaintenanceWindow } from '@/shared/api/types'

function getNextFirings(cronExpr: string, n = 3): string[] {
  try {
    const interval = parseExpression(cronExpr)
    return Array.from({ length: n }, () => {
      const d = interval.next().toDate()
      return d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })
    })
  } catch {
    return []
  }
}

const scheduleSchema = z
  .object({
    name: z.string().min(2, 'Name required').max(200),
    scope_type: z.enum(['CAMERA', 'ZONE']),
    scope_id: z.coerce.number().int().positive(),
    schedule_type: z.enum(['ONE_TIME', 'RECURRING']),
    starts_at: z.string().optional(),
    ends_at: z.string().optional(),
    cron_expr: z.string().optional(),
    duration_minutes: z.coerce.number().int().positive().optional().or(z.literal('')),
    reason: z.string().optional(),
  })
  .superRefine((data, ctx) => {
    if (data.schedule_type === 'ONE_TIME') {
      if (!data.starts_at) {
        ctx.addIssue({ code: 'custom', path: ['starts_at'], message: 'Start time required' })
      }
      if (!data.ends_at) {
        ctx.addIssue({ code: 'custom', path: ['ends_at'], message: 'End time required' })
      }
    } else {
      if (!data.cron_expr) {
        ctx.addIssue({ code: 'custom', path: ['cron_expr'], message: 'Cron expression required' })
      }
      if (!data.duration_minutes) {
        ctx.addIssue({
          code: 'custom',
          path: ['duration_minutes'],
          message: 'Duration required',
        })
      }
    }
  })

type ScheduleForm = z.infer<typeof scheduleSchema>

export function MaintenanceCalendarPage() {
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)

  const { data: windows = [], isLoading } = useQuery<MaintenanceWindow[]>({
    queryKey: ['admin', 'maintenance'],
    queryFn: () => api.get('/api/maintenance'),
  })

  const {
    register,
    handleSubmit,
    watch,
    control,
    reset,
    formState: { errors },
  } = useForm<ScheduleForm>({
    resolver: zodResolver(scheduleSchema),
    defaultValues: { schedule_type: 'ONE_TIME', scope_type: 'CAMERA' },
  })

  const createMutation = useMutation({
    mutationFn: (data: ScheduleForm) =>
      api.post('/api/maintenance', {
        ...data,
        duration_minutes: data.duration_minutes || null,
      }),
    onSuccess: () => {
      reset()
      setShowCreate(false)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'maintenance'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (windowId: number) => api.delete(`/api/maintenance/${windowId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'maintenance'] })
    },
  })

  const scheduleType = watch('schedule_type')
  const cronExpr = watch('cron_expr') ?? ''
  const cronFirings = scheduleType === 'RECURRING' && cronExpr ? getNextFirings(cronExpr) : []

  return (
    <>
      <Helmet title="Maintenance — Admin" />
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-[22px] font-semibold text-text-primary">Maintenance Windows</h1>
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600"
          >
            Schedule Window
          </button>
        </div>

        {deleteMutation.isError && (
          <p role="alert" className="mb-3 text-[13px] text-error">
            Failed to delete maintenance window. Please try again.
          </p>
        )}

        {isLoading && (
          <p role="status" aria-label="Loading maintenance windows">
            Loading…
          </p>
        )}

        {!isLoading && (
          <div className="rounded border border-border overflow-hidden">
            <table className="w-full text-[14px]">
              <thead className="bg-surface-sunken border-b border-border">
                <tr>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-muted uppercase">
                    Name
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-muted uppercase">
                    Scope
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-muted uppercase">
                    Schedule
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-muted uppercase">
                    Status
                  </th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {windows.map((w) => (
                  <tr key={w.window_id} className="hover:bg-surface-raised">
                    <td className="px-4 py-3 font-medium text-text-primary">{w.name}</td>
                    <td className="px-4 py-3 text-text-secondary">
                      {w.scope_type} #{w.scope_id}
                    </td>
                    <td className="px-4 py-3 text-text-secondary font-mono text-[12px]">
                      {w.cron_expr ?? (w.starts_at ? w.starts_at.slice(0, 16) : '—')}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-[11px] font-medium ${
                          w.is_active
                            ? 'bg-brand-100 text-brand-700'
                            : 'bg-surface-sunken text-text-muted'
                        }`}
                      >
                        {w.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        aria-label={`Delete ${w.name}`}
                        onClick={() => deleteMutation.mutate(w.window_id)}
                        disabled={deleteMutation.isPending}
                        className="text-[13px] text-error hover:underline"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
                {windows.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-6 text-center text-[14px] text-text-muted"
                    >
                      No maintenance windows scheduled.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showCreate && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Schedule maintenance window"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        >
          <div className="bg-surface-base rounded-lg shadow-lg w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
            <h2 className="text-[17px] font-semibold text-text-primary mb-4">
              Schedule Maintenance Window
            </h2>
            <form
              aria-label="Schedule maintenance form"
              onSubmit={handleSubmit((d) => createMutation.mutate(d))}
              className="space-y-4"
            >
              <div>
                <label
                  htmlFor="maint-name"
                  className="block text-[13px] font-medium text-text-secondary mb-1"
                >
                  Name
                </label>
                <input
                  id="maint-name"
                  {...register('name')}
                  className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder="Nightly backup window"
                />
                {errors.name && (
                  <p role="alert" className="mt-1 text-[12px] text-error">
                    {errors.name.message}
                  </p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label
                    htmlFor="maint-scope-type"
                    className="block text-[13px] font-medium text-text-secondary mb-1"
                  >
                    Scope type
                  </label>
                  <select
                    id="maint-scope-type"
                    {...register('scope_type')}
                    className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base focus:outline-none"
                  >
                    <option value="CAMERA">CAMERA</option>
                    <option value="ZONE">ZONE</option>
                  </select>
                </div>
                <div>
                  <label
                    htmlFor="maint-scope-id"
                    className="block text-[13px] font-medium text-text-secondary mb-1"
                  >
                    Scope ID
                  </label>
                  <input
                    id="maint-scope-id"
                    type="number"
                    {...register('scope_id')}
                    className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base focus:outline-none"
                    placeholder="1"
                  />
                </div>
              </div>

              {/* Schedule type toggle */}
              <div>
                <p className="block text-[13px] font-medium text-text-secondary mb-2">
                  Schedule type
                </p>
                <div className="flex gap-2" role="group" aria-label="Schedule type">
                  <Controller
                    control={control}
                    name="schedule_type"
                    render={({ field }) => (
                      <>
                        <button
                          type="button"
                          aria-pressed={field.value === 'ONE_TIME'}
                          onClick={() => field.onChange('ONE_TIME')}
                          className={`px-4 py-2 text-[13px] rounded border transition-colors ${
                            field.value === 'ONE_TIME'
                              ? 'bg-brand-500 text-white border-brand-500'
                              : 'border-border text-text-secondary hover:text-text-primary'
                          }`}
                        >
                          One-time
                        </button>
                        <button
                          type="button"
                          aria-pressed={field.value === 'RECURRING'}
                          onClick={() => field.onChange('RECURRING')}
                          className={`px-4 py-2 text-[13px] rounded border transition-colors ${
                            field.value === 'RECURRING'
                              ? 'bg-brand-500 text-white border-brand-500'
                              : 'border-border text-text-secondary hover:text-text-primary'
                          }`}
                        >
                          Recurring
                        </button>
                      </>
                    )}
                  />
                </div>
              </div>

              {scheduleType === 'ONE_TIME' && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label
                      htmlFor="maint-starts-at"
                      className="block text-[13px] font-medium text-text-secondary mb-1"
                    >
                      Start
                    </label>
                    <input
                      id="maint-starts-at"
                      type="datetime-local"
                      {...register('starts_at')}
                      className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base focus:outline-none"
                    />
                    {errors.starts_at && (
                      <p role="alert" className="mt-1 text-[12px] text-error">
                        {errors.starts_at.message}
                      </p>
                    )}
                  </div>
                  <div>
                    <label
                      htmlFor="maint-ends-at"
                      className="block text-[13px] font-medium text-text-secondary mb-1"
                    >
                      End
                    </label>
                    <input
                      id="maint-ends-at"
                      type="datetime-local"
                      {...register('ends_at')}
                      className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base focus:outline-none"
                    />
                    {errors.ends_at && (
                      <p role="alert" className="mt-1 text-[12px] text-error">
                        {errors.ends_at.message}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {scheduleType === 'RECURRING' && (
                <div className="space-y-3">
                  <div>
                    <label
                      htmlFor="maint-cron"
                      className="block text-[13px] font-medium text-text-secondary mb-1"
                    >
                      Cron expression
                    </label>
                    <input
                      id="maint-cron"
                      {...register('cron_expr')}
                      className="w-full border border-border rounded px-3 py-2 text-[14px] font-mono bg-surface-base focus:outline-none focus:ring-2 focus:ring-brand-500"
                      placeholder="0 2 * * *"
                    />
                    {errors.cron_expr && (
                      <p role="alert" className="mt-1 text-[12px] text-error">
                        {errors.cron_expr.message}
                      </p>
                    )}
                    {cronFirings.length > 0 && (
                      <ul
                        aria-label="Next 3 firings"
                        className="mt-2 space-y-1"
                      >
                        {cronFirings.map((firing, i) => (
                          <li key={i} className="text-[12px] font-mono text-text-muted">
                            {i + 1}. {firing}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <div>
                    <label
                      htmlFor="maint-duration"
                      className="block text-[13px] font-medium text-text-secondary mb-1"
                    >
                      Duration (minutes)
                    </label>
                    <input
                      id="maint-duration"
                      type="number"
                      {...register('duration_minutes')}
                      className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base focus:outline-none"
                      placeholder="60"
                    />
                    {errors.duration_minutes && (
                      <p role="alert" className="mt-1 text-[12px] text-error">
                        {errors.duration_minutes.message}
                      </p>
                    )}
                  </div>
                </div>
              )}

              {createMutation.isError && (
                <p role="alert" className="text-[13px] text-error">
                  Failed to schedule maintenance window.
                </p>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => { reset(); setShowCreate(false) }}
                  className="px-4 py-2 text-[14px] rounded border border-border text-text-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50"
                >
                  {createMutation.isPending ? 'Scheduling…' : 'Schedule'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
