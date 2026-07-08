import { useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { MapPin } from 'lucide-react'
import { Icon } from '@/shared/design-system/icons'
import { api } from '@/shared/api/client'
import type { ZoneResponse } from '@/shared/api/types'
import { EmptyState } from './components/EmptyState'
import { SkeletonTable } from '@/shared/design-system/components/Skeleton'

const zoneSchema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters').max(200),
  loiter_threshold_s: z.coerce.number().min(1, 'Must be at least 1 second'),
  max_capacity: z.coerce.number().int().min(1).optional().or(z.literal('')),
  allowed_hours: z.string().optional().or(z.literal('')),
})

type ZoneForm = z.infer<typeof zoneSchema>

export function ZoneEditorPage() {
  const queryClient = useQueryClient()
  const [editingZone, setEditingZone] = useState<ZoneResponse | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ZoneResponse | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [showAdd, setShowAdd] = useState(false)

  const { data: zones = [], isLoading } = useQuery<ZoneResponse[]>({
    queryKey: ['admin', 'zones'],
    queryFn: () => api.get('/api/zones'),
  })

  const {
    register: registerAdd,
    handleSubmit: handleAddSubmit,
    reset: resetAdd,
    formState: { errors: addErrors },
  } = useForm<ZoneForm>({ resolver: zodResolver(zoneSchema), defaultValues: { loiter_threshold_s: 30 } })

  const {
    register: registerEdit,
    handleSubmit: handleEditSubmit,
    reset: resetEdit,
    formState: { errors: editErrors },
  } = useForm<ZoneForm>({ resolver: zodResolver(zoneSchema) })

  const createMutation = useMutation({
    mutationFn: (data: ZoneForm) =>
      api.post('/api/zones', {
        name: data.name,
        loiter_threshold_s: data.loiter_threshold_s,
        max_capacity: data.max_capacity || null,
        allowed_hours: data.allowed_hours || null,
        polygon: [],
      }),
    onSuccess: () => {
      resetAdd()
      setShowAdd(false)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'zones'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ zoneId, data }: { zoneId: number; data: ZoneForm }) =>
      api.patch(`/api/zones/${zoneId}`, {
        name: data.name,
        loiter_threshold_s: data.loiter_threshold_s,
        max_capacity: data.max_capacity || null,
        allowed_hours: data.allowed_hours || null,
      }),
    onSuccess: () => {
      setEditingZone(null)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'zones'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (zoneId: number) => api.delete(`/api/zones/${zoneId}`),
    onSuccess: () => {
      setDeleteTarget(null)
      setDeleteConfirm('')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'zones'] })
    },
  })

  function handleEditClick(zone: ZoneResponse) {
    setEditingZone(zone)
    resetEdit({
      name: zone.name,
      loiter_threshold_s: zone.loiter_threshold_s,
      max_capacity: zone.max_capacity ?? undefined,
      allowed_hours: zone.allowed_hours ?? undefined,
    })
  }

  return (
    <>
      <Helmet title="Zones — Admin" />
      <div className="p-6">
        <div className="mb-5 flex items-center justify-between">
          <h1 className="text-[22px] font-bold text-text-primary">Zones</h1>
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="inline-flex items-center gap-1.5 h-10 rounded-[10px] bg-action-700 px-4 text-[13px] font-medium text-white hover:bg-action-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus-ring)]"
          >
            <Icon.add className="h-4 w-4" aria-hidden="true" />
            Add Zone
          </button>
        </div>

        {isLoading && (
          <div role="status" aria-label="Loading zones">
            <SkeletonTable rows={4} />
          </div>
        )}

        {!isLoading && zones.length === 0 && (
          <EmptyState
            icon={MapPin}
            title="No zones defined"
            description="Draw zones on the floor plan to track dwell time and restrict access."
            cta={
              <button
                type="button"
                onClick={() => setShowAdd(true)}
                className="inline-flex items-center gap-1.5 h-9 rounded-[10px] bg-action-700 px-4 text-[13px] font-medium text-white hover:bg-action-800"
              >
                <Icon.add className="h-4 w-4" aria-hidden="true" />
                Add Zone
              </button>
            }
          />
        )}

        {!isLoading && zones.length > 0 && (
          <div className="rounded-xl border border-border overflow-hidden">
            <table className="w-full text-[14px]">
              <thead className="bg-surface-sunken border-b border-border">
                <tr>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Name
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Loiter Threshold
                  </th>
                  <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em]">
                    Max Capacity
                  </th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {zones.map((zone) => (
                  <tr key={zone.zone_id} className="hover:bg-surface-raised">
                    <td className="px-4 py-3 font-medium text-text-primary">{zone.name}</td>
                    <td className="px-4 py-3 text-[13px] text-text-secondary">{zone.loiter_threshold_s}s</td>
                    <td className="px-4 py-3 text-[13px] text-text-secondary">
                      {zone.max_capacity ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      <button
                        type="button"
                        aria-label={`Edit ${zone.name}`}
                        onClick={() => handleEditClick(zone)}
                        className="rounded-[10px] px-2 py-1 text-[13px] text-text-primary hover:bg-surface-raised transition-colors"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        aria-label={`Delete ${zone.name}`}
                        onClick={() => setDeleteTarget(zone)}
                        className="rounded-[10px] px-2 py-1 text-[13px] text-error hover:bg-error/10 transition-colors"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add zone dialog */}
      {showAdd && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Add zone"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        >
          <div className="w-full max-w-md rounded-xl bg-surface-base p-6 shadow-lg">
            <h2 className="mb-4 text-[17px] font-semibold text-text-primary">Add Zone</h2>
            <form
              aria-label="Add zone form"
              onSubmit={handleAddSubmit((d) => createMutation.mutate(d))}
              className="space-y-4"
            >
              <div>
                <label
                  htmlFor="zone-name"
                  className="mb-1 block text-[13px] font-medium text-text-secondary"
                >
                  Zone name
                </label>
                <input
                  id="zone-name"
                  {...registerAdd('name')}
                  className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] text-text-primary focus:border-brand-500 focus:outline-none"
                  placeholder="Assembly Line"
                />
                {addErrors.name && (
                  <p role="alert" className="mt-1 text-[12px] text-error">
                    {addErrors.name.message}
                  </p>
                )}
              </div>
              <div>
                <label
                  htmlFor="zone-loiter"
                  className="mb-1 block text-[13px] font-medium text-text-secondary"
                >
                  Loiter threshold (seconds)
                </label>
                <input
                  id="zone-loiter"
                  type="number"
                  {...registerAdd('loiter_threshold_s')}
                  className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] text-text-primary focus:border-brand-500 focus:outline-none"
                />
                {addErrors.loiter_threshold_s && (
                  <p role="alert" className="mt-1 text-[12px] text-error">
                    {addErrors.loiter_threshold_s.message}
                  </p>
                )}
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => { resetAdd(); setShowAdd(false) }}
                  className="h-10 rounded-[10px] border border-border px-4 text-[13px] text-text-secondary hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="h-10 rounded-[10px] bg-action-700 px-4 text-[13px] font-medium text-white hover:bg-action-800 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
                >
                  {createMutation.isPending ? 'Saving…' : 'Add Zone'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit zone dialog */}
      {editingZone && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Edit ${editingZone.name}`}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        >
          <div className="w-full max-w-md rounded-xl bg-surface-base p-6 shadow-lg">
            <h2 className="mb-4 text-[17px] font-semibold text-text-primary">
              Edit Zone: {editingZone.name}
            </h2>
            <form
              aria-label="Edit zone form"
              onSubmit={handleEditSubmit((d) =>
                updateMutation.mutate({ zoneId: editingZone.zone_id, data: d }),
              )}
              className="space-y-4"
            >
              <div>
                <label
                  htmlFor="edit-zone-name"
                  className="mb-1 block text-[13px] font-medium text-text-secondary"
                >
                  Zone name
                </label>
                <input
                  id="edit-zone-name"
                  {...registerEdit('name')}
                  className="h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] text-text-primary focus:border-brand-500 focus:outline-none"
                />
                {editErrors.name && (
                  <p role="alert" className="mt-1 text-[12px] text-error">
                    {editErrors.name.message}
                  </p>
                )}
              </div>
              {updateMutation.isError && (
                <p role="alert" className="text-[13px] text-error">
                  Failed to save zone. Please try again.
                </p>
              )}
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditingZone(null)}
                  className="h-10 rounded-[10px] border border-border px-4 text-[13px] text-text-secondary hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={updateMutation.isPending}
                  className="h-10 rounded-[10px] bg-action-700 px-4 text-[13px] font-medium text-white hover:bg-action-800 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
                >
                  {updateMutation.isPending ? 'Saving…' : 'Save'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete confirmation */}
      {deleteTarget && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Confirm delete ${deleteTarget.name}`}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        >
          <div className="w-full max-w-sm rounded-xl bg-surface-base p-6 shadow-xl">
            <div className="mb-4 rounded-xl border border-error/20 bg-error/5 p-4">
              <p className="text-[15px] font-semibold text-text-primary">
                Delete zone "{deleteTarget.name}"?
              </p>
              <p className="mt-1 text-[13px] text-text-secondary">
                This action cannot be undone. Type the zone name to confirm.
              </p>
            </div>
            <input
              type="text"
              aria-label="Type zone name to confirm"
              value={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.value)}
              placeholder={deleteTarget.name}
              className="mb-4 h-10 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[14px] text-text-primary focus:border-brand-500 focus:outline-none"
            />
            {deleteMutation.isError && (
              <p role="alert" className="mb-3 text-[13px] text-error">
                Failed to delete zone. Please try again.
              </p>
            )}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => { setDeleteTarget(null); setDeleteConfirm('') }}
                className="h-10 rounded-[10px] border border-border px-4 text-[13px] text-text-secondary hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => deleteMutation.mutate(deleteTarget.zone_id)}
                disabled={deleteConfirm !== deleteTarget.name || deleteMutation.isPending}
                className="h-10 rounded-[10px] bg-error px-4 text-[13px] font-medium text-white hover:bg-error/90 disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
              >
                {deleteMutation.isPending ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
