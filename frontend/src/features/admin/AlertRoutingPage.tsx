import { useState, useMemo } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { type ColumnDef } from '@tanstack/react-table'
import { Icon } from '@/shared/design-system/icons'
import { api } from '@/shared/api/client'
import type { AlertRoutingRule } from '@/shared/api/types'
import { EmptyState } from './components/EmptyState'
import { SkeletonTable } from '@/shared/design-system/components/Skeleton'
import { PageHeader } from '@/shared/design-system/components/PageHeader'
import { Button } from '@/shared/design-system/components/Button'
import { DataTable } from '@/shared/design-system/components/DataTable'
import { Switch } from '@/shared/design-system/components/ui/Switch'

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

const CHANNEL_BADGE: Record<string, string> = {
  email: 'bg-info/10 text-info',
  slack: 'bg-success/10 text-success',
  telegram: 'bg-info/10 text-info',
  webhook: 'bg-warning/10 text-warning',
}

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

  const columns = useMemo<ColumnDef<AlertRoutingRule, unknown>[]>(
    () => [
      {
        accessorKey: 'channel',
        header: 'Channel',
        cell: ({ getValue }) => {
          const ch = getValue() as string
          return (
            <span
              className={`inline-block rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ${
                CHANNEL_BADGE[ch] ?? 'bg-surface-sunken text-text-muted'
              }`}
            >
              {ch}
            </span>
          )
        },
      },
      {
        accessorKey: 'target',
        header: 'Target',
        cell: ({ getValue }) => (
          <span className="font-mono text-[12px] text-text-secondary max-w-xs truncate block">
            {getValue() as string}
          </span>
        ),
      },
      {
        accessorKey: 'alert_type',
        header: 'Alert Type',
        cell: ({ getValue }) => (
          <span className="text-[13px] text-text-secondary">
            {(getValue() as string | null) ?? 'All'}
          </span>
        ),
      },
      {
        accessorKey: 'is_active',
        header: 'Active',
        enableSorting: false,
        cell: ({ row }) => (
          <Switch
            checked={row.original.is_active}
            onCheckedChange={(checked) =>
              toggleMutation.mutate({ id: row.original.routing_id, active: checked })
            }
            disabled={toggleMutation.isPending}
            aria-label={`${row.original.is_active ? 'Deactivate' : 'Activate'} rule ${row.original.routing_id}`}
          />
        ),
      },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row }) => (
          <button
            type="button"
            aria-label={`Delete rule ${row.original.routing_id}`}
            onClick={() => deleteMutation.mutate(row.original.routing_id)}
            className="rounded-[10px] px-2 py-1 text-[13px] text-error hover:bg-error/10 transition-colors"
          >
            Delete
          </button>
        ),
      },
    ],
    [toggleMutation, deleteMutation],
  )

  return (
    <>
      <Helmet title="Alert Routing — Admin" />
      <div className="p-6">
        <PageHeader
          title="Alert Routing"
          actions={
            <Button onClick={() => setShowAdd(true)} icon={<Icon.add className="h-4 w-4" aria-hidden="true" />}>
              Add Rule
            </Button>
          }
        />

        {(deleteMutation.isError || toggleMutation.isError) && (
          <p role="alert" className="mb-3 text-[13px] text-error">
            {deleteMutation.isError ? 'Failed to delete rule.' : 'Failed to update rule.'} Please try again.
          </p>
        )}

        {isLoading && (
          <div role="status" aria-label="Loading routing rules">
            <SkeletonTable rows={6} />
          </div>
        )}

        {!isLoading && rules.length === 0 && (
          <EmptyState
            icon={Icon.alert}
            title="No routing rules configured"
            description="Create a rule to route alerts to email, Slack, Telegram, or webhook."
            cta={
              <Button onClick={() => setShowAdd(true)} icon={<Icon.add className="h-4 w-4" aria-hidden="true" />}>
                Add Rule
              </Button>
            }
          />
        )}

        {!isLoading && rules.length > 0 && (
          <DataTable
            tableId="alert-routing"
            columns={columns}
            data={rules}
            filterPlaceholder="Filter routing rules…"
            pageSize={20}
          />
        )}
      </div>

      {showAdd && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Add routing rule"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        >
          <div className="w-full max-w-md rounded-xl bg-surface-base p-6 shadow-lg">
            <h2 className="mb-4 text-[17px] font-semibold text-text-primary">Add Routing Rule</h2>
            <form
              aria-label="Add routing rule form"
              onSubmit={handleSubmit((d) => createMutation.mutate(d))}
              className="space-y-4"
            >
              <div>
                <label
                  htmlFor="rule-channel"
                  className="mb-1 block text-[13px] font-medium text-text-secondary"
                >
                  Channel
                </label>
                <select
                  id="rule-channel"
                  {...register('channel')}
                  className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] text-text-primary focus:border-brand-500 focus:outline-none"
                >
                  <option value="">Select channel…</option>
                  <option value="email">Email</option>
                  <option value="slack">Slack</option>
                  <option value="telegram">Telegram</option>
                  <option value="webhook">Webhook</option>
                </select>
                {errors.channel && (
                  <p role="alert" className="mt-1 text-[12px] text-error">
                    {errors.channel.message}
                  </p>
                )}
              </div>
              <div>
                <label
                  htmlFor="rule-target"
                  className="mb-1 block text-[13px] font-medium text-text-secondary"
                >
                  Target
                  {channel === 'webhook' && (
                    <span className="ml-1 font-normal text-text-muted">(must be https://)</span>
                  )}
                </label>
                <input
                  id="rule-target"
                  {...register('target')}
                  className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] text-text-primary focus:border-brand-500 focus:outline-none"
                  placeholder={
                    channel === 'email'
                      ? 'security@company.com'
                      : channel === 'webhook'
                        ? 'https://hooks.example.com/…'
                        : ''
                  }
                />
                {errors.target && (
                  <p role="alert" className="mt-1 text-[12px] text-error">
                    {errors.target.message}
                  </p>
                )}
              </div>
              <div>
                <label
                  htmlFor="rule-alert-type"
                  className="mb-1 block text-[13px] font-medium text-text-secondary"
                >
                  Alert type <span className="font-normal text-text-muted">(optional — blank = all)</span>
                </label>
                <select
                  id="rule-alert-type"
                  {...register('alert_type')}
                  className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] text-text-primary focus:border-brand-500 focus:outline-none"
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
                <p role="alert" className="text-[13px] text-error">
                  Failed to add rule. Please try again.
                </p>
              )}
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => { reset(); setShowAdd(false) }}
                  className="h-10 rounded-[10px] border border-border px-4 text-[13px] text-text-secondary hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="h-10 rounded-[10px] bg-action-700 px-4 text-[13px] font-medium text-white hover:bg-action-800 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
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
