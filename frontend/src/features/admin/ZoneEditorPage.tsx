import { useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { api } from '@/shared/api/client'
import type { ZoneResponse } from '@/shared/api/types'

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
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-[22px] font-semibold text-text-primary">Zones</h1>
          <button
            type="button"
            onClick={() => setShowAdd(true)}
            className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600"
          >
            Add Zone
          </button>
        </div>

        {isLoading && (
          <p role="status" aria-label="Loading zones">
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
                    Loiter Threshold
                  </th>
                  <th className="text-left px-4 py-2 text-[12px] font-semibold text-text-muted uppercase">
                    Max Capacity
                  </th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {zones.map((zone) => (
                  <tr key={zone.zone_id} className="hover:bg-surface-raised">
                    <td className="px-4 py-3 font-medium text-text-primary">{zone.name}</td>
                    <td className="px-4 py-3 text-text-secondary">{zone.loiter_threshold_s}s</td>
                    <td className="px-4 py-3 text-text-secondary">
                      {zone.max_capacity ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      <button
                        type="button"
                        aria-label={`Edit ${zone.name}`}
                        onClick={() => handleEditClick(zone)}
                        className="text-[13px] text-brand-600 hover:underline"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        aria-label={`Delete ${zone.name}`}
                        onClick={() => setDeleteTarget(zone)}
                        className="text-[13px] text-error hover:underline"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
                {zones.length === 0 && (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-6 text-center text-[14px] text-text-muted"
                    >
                      No zones defined.
                    </td>
                  </tr>
                )}
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
          <div className="bg-surface-base rounded-lg shadow-lg w-full max-w-md p-6">
            <h2 className="text-[17px] font-semibold text-text-primary mb-4">Add Zone</h2>
            <form
              aria-label="Add zone form"
              onSubmit={handleAddSubmit((d) => createMutation.mutate(d))}
              className="space-y-4"
            >
              <div>
                <label
                  htmlFor="zone-name"
                  className="block text-[13px] font-medium text-text-secondary mb-1"
                >
                  Zone name
                </label>
                <input
                  id="zone-name"
                  {...registerAdd('name')}
                  className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base focus:outline-none focus:ring-2 focus:ring-brand-500"
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
                  className="block text-[13px] font-medium text-text-secondary mb-1"
                >
                  Loiter threshold (seconds)
                </label>
                <input
                  id="zone-loiter"
                  type="number"
                  {...registerAdd('loiter_threshold_s')}
                  className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base focus:outline-none focus:ring-2 focus:ring-brand-500"
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
                  className="px-4 py-2 text-[14px] rounded border border-border text-text-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50"
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
          <div className="bg-surface-base rounded-lg shadow-lg w-full max-w-md p-6">
            <h2 className="text-[17px] font-semibold text-text-primary mb-4">
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
                  className="block text-[13px] font-medium text-text-secondary mb-1"
                >
                  Zone name
                </label>
                <input
                  id="edit-zone-name"
                  {...registerEdit('name')}
                  className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base focus:outline-none focus:ring-2 focus:ring-brand-500"
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
                  className="px-4 py-2 text-[14px] rounded border border-border text-text-secondary"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={updateMutation.isPending}
                  className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50"
                >
                  Save
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
          <div className="bg-surface-base rounded-lg shadow-xl w-full max-w-sm p-6">
            <p className="text-[15px] font-medium text-text-primary mb-2">
              Delete zone "{deleteTarget.name}"?
            </p>
            <p className="text-[13px] text-text-secondary mb-3">
              Type the zone name to confirm deletion.
            </p>
            <input
              type="text"
              aria-label="Type zone name to confirm"
              value={deleteConfirm}
              onChange={(e) => setDeleteConfirm(e.target.value)}
              placeholder={deleteTarget.name}
              className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base mb-4 focus:outline-none"
            />
            {deleteMutation.isError && (
              <p role="alert" className="mb-3 text-[13px] text-error">
                Failed to delete zone. Please try again.
              </p>
            )}
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                onClick={() => { setDeleteTarget(null); setDeleteConfirm('') }}
                className="px-4 py-2 text-[14px] rounded border border-border text-text-secondary"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => deleteMutation.mutate(deleteTarget.zone_id)}
                disabled={deleteConfirm !== deleteTarget.name || deleteMutation.isPending}
                className="px-4 py-2 text-[14px] rounded bg-destructive text-white hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
