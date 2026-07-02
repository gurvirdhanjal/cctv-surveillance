import { useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { api } from '@/shared/api/client'
import type { AlertRoutingRule } from '@/shared/api/types'

const routingSchema = z
  .object({
    channel: z.enum(['email', 'slack', 'telegram', 'webhook'], {
      required_error: 'Channel required',
    }),
    target: z.string().min(1, 'Target required'),
    alert_type: z.string().optional().or(z.literal('')),
    severity: z.string().optional().or(z.literal('')),
    zone_id: z.coerce.number().int().positive().optional().or(z.literal('')),
  })
  .superRefine((data, ctx) => {
    if (data.channel === 'webhook' && !data.target.startsWith('https://')) {
      ctx.addIssue({
        code: 'custom',
        path: ['target'],
        message: 'Webhook target must start with https://',
      })
    }
  })

type RoutingForm = z.infer<typeof routingSchema>

export function AlertRoutingPage() {
  const queryClient = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)

  const { data: rules = [], isLoading } = useQuery<AlertRoutingRule[]>({
    queryKey: ['admin', 'alert-routing'],
    queryFn: () => api.get('/api/alert-routing'),
  })

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<RoutingForm>({ resolver: zodResolver(routingSchema) })

  const createMutation = useMutation({
    mutationFn: (data: RoutingForm) =>
      api.post('/api/alert-routing', {
        channel: data.channel,
        target: data.target,
        alert_type: data.alert_type || null,
        severity: data.severity || null,
        zone_id: data.zone_id || null,
      }),
    onSuccess: () => {
      reset()
      setShowAdd(false)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'alert-routing'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (routingId: number) => api.delete(`/api/alert-routing/${routingId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'alert-routing'] })
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      api.patch(`/api/alert-routing/${id}`, { is_active: active }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'alert-routing'] })
    },
  })

  const channel = watch('channel')

  return (
    <>
      <Helmet title="Alert Routing — Admin" />
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-[22px] font-semibold text-text-primary">Alert Routing</h1>
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600"
          >
            Add Rule
          </button>
        </div>

        {isLoading && (
          <p role="status" aria-label="Loading routing rules">
            Loading…
          </p>
        )}

        {!isLoading && (
          <div className="rounded border border-border-subtle overflow-hidden">
            <table className="w-full text-[14px]">
              <thead className="bg-surface-sunken border-b border-border-subtle">
                <tr>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-tertiary uppercase">
                    Channel
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-tertiary uppercase">
                    Target
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-tertiary uppercase">
                    Alert Type
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-tertiary uppercase">
                    Active
                  </th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {rules.map((r) => (
                  <tr key={r.routing_id} className="hover:bg-surface-hover">
                    <td className="px-4 py-3 font-medium text-text-primary capitalize">
                      {r.channel}
                    </td>
                    <td className="px-4 py-3 font-mono text-[12px] text-text-secondary max-w-xs truncate">
                      {r.target}
                    </td>
                    <td className="px-4 py-3 text-text-secondary">{r.alert_type ?? 'All'}</td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        role="switch"
                        aria-checked={r.is_active}
                        aria-label={`${r.is_active ? 'Deactivate' : 'Activate'} rule ${r.routing_id}`}
                        onClick={() =>
                          toggleMutation.mutate({ id: r.routing_id, active: !r.is_active })
                        }
                        disabled={toggleMutation.isPending}
                        className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none disabled:opacity-50 ${
                          r.is_active ? 'bg-brand-500' : 'bg-surface-sunken border border-border-subtle'
                        }`}
                      >
                        <span
                          className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform ${
                            r.is_active ? 'translate-x-4' : 'translate-x-0.5'
                          }`}
                        />
                      </button>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        aria-label={`Delete rule ${r.routing_id}`}
                        onClick={() => deleteMutation.mutate(r.routing_id)}
                        className="text-[13px] text-red-600 hover:underline"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
                {rules.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-6 text-center text-[14px] text-text-tertiary"
                    >
                      No routing rules configured.
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
          aria-label="Add routing rule"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        >
          <div className="bg-surface-base rounded-lg shadow-lg w-full max-w-md p-6">
            <h2 className="text-[17px] font-semibold text-text-primary mb-4">Add Routing Rule</h2>
            <form
              aria-label="Add routing rule form"
              onSubmit={handleSubmit((d) => createMutation.mutate(d))}
              className="space-y-4"
            >
              <div>
                <label
                  htmlFor="rule-channel"
                  className="block text-[13px] font-medium text-text-secondary mb-1"
                >
                  Channel
                </label>
                <select
                  id="rule-channel"
                  {...register('channel')}
                  className="w-full border border-border-subtle rounded px-3 py-2 text-[14px] bg-surface-base focus:outline-none focus:ring-2 focus:ring-brand-500"
                >
                  <option value="">Select channel…</option>
                  <option value="email">Email</option>
                  <option value="slack">Slack</option>
                  <option value="telegram">Telegram</option>
                  <option value="webhook">Webhook</option>
                </select>
                {errors.channel && (
                  <p role="alert" className="mt-1 text-[12px] text-red-600">
                    {errors.channel.message}
                  </p>
                )}
              </div>
              <div>
                <label
                  htmlFor="rule-target"
                  className="block text-[13px] font-medium text-text-secondary mb-1"
                >
                  Target
                  {channel === 'webhook' && (
                    <span className="ml-1 text-[11px] text-text-tertiary">(must be https://)</span>
                  )}
                </label>
                <input
                  id="rule-target"
                  {...register('target')}
                  className="w-full border border-border-subtle rounded px-3 py-2 text-[14px] bg-surface-base focus:outline-none focus:ring-2 focus:ring-brand-500"
                  placeholder={
                    channel === 'email'
                      ? 'security@company.com'
                      : channel === 'webhook'
                        ? 'https://hooks.example.com/…'
                        : ''
                  }
                />
                {errors.target && (
                  <p role="alert" className="mt-1 text-[12px] text-red-600">
                    {errors.target.message}
                  </p>
                )}
              </div>
              <div>
                <label
                  htmlFor="rule-alert-type"
                  className="block text-[13px] font-medium text-text-secondary mb-1"
                >
                  Alert type (optional — leave blank for all)
                </label>
                <select
                  id="rule-alert-type"
                  {...register('alert_type')}
                  className="w-full border border-border-subtle rounded px-3 py-2 text-[14px] bg-surface-base focus:outline-none"
                >
                  <option value="">All types</option>
                  <option value="UNKNOWN_PERSON">UNKNOWN_PERSON</option>
                  <option value="INTRUSION">INTRUSION</option>
                  <option value="LOITERING">LOITERING</option>
                  <option value="VIOLENCE">VIOLENCE</option>
                  <option value="PPE_VIOLATION">PPE_VIOLATION</option>
                  <option value="SYSTEM_CRITICAL">SYSTEM_CRITICAL</option>
                </select>
              </div>
              {createMutation.isError && (
                <p role="alert" className="text-[13px] text-red-600">
                  Failed to add rule.
                </p>
              )}
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => { reset(); setShowAdd(false) }}
                  className="px-4 py-2 text-[14px] rounded border border-border-subtle text-text-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50"
                >
                  {createMutation.isPending ? 'Adding…' : 'Add Rule'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  )
}
