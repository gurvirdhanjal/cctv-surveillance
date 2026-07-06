import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { ResolvedConfigResponse } from '@/shared/api/types'

interface Props {
  cameraId: number
}

export function OverridesTab({ cameraId }: Props) {
  const queryClient = useQueryClient()
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)

  const { data, isLoading } = useQuery<ResolvedConfigResponse>({
    queryKey: ['admin', 'cameras', cameraId, 'resolved-config'],
    queryFn: () => api.get(`/api/cameras/${cameraId}/resolved-config`),
  })

  const saveMutation = useMutation({
    mutationFn: (overrides: Record<string, unknown>) =>
      api.patch(`/api/cameras/${cameraId}/overrides`, { overrides }),
    onSuccess: () => {
      setShowAdd(false)
      setNewKey('')
      setNewValue('')
      setAddError(null)
      void queryClient.invalidateQueries({
        queryKey: ['admin', 'cameras', cameraId, 'resolved-config'],
      })
    },
    onError: () => setAddError('Failed to save override.'),
  })

  const settings = data?.settings ?? {}
  const overriddenSettings = Object.entries(settings).filter(
    ([, item]) => item.source !== 'global_default',
  )
  const hasShutterOverride = overriddenSettings.some(([key]) => key.startsWith('shutter'))

  function handleAddOverride() {
    if (!newKey.trim()) {
      setAddError('Key is required.')
      return
    }
    let parsedValue: unknown = newValue
    try {
      parsedValue = JSON.parse(newValue)
    } catch {
      // keep as string
    }
    saveMutation.mutate({ [newKey.trim()]: parsedValue })
  }

  return (
    <div className="space-y-4">
      {hasShutterOverride && (
        <div
          role="status"
          aria-label="Shutter override warning"
          className="flex items-start gap-2 rounded-xl border border-warning/20 bg-warning/10 p-3 text-[13px] text-warning"
        >
          <span aria-hidden="true">⚠</span>
          <span>
            Shutter-type overrides are set. Verify the override matches the physical camera sensor
            before saving.
          </span>
        </div>
      )}

      <div className="flex items-center justify-between">
        <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">
          Per-camera overrides
        </h2>
        <button
          type="button"
          onClick={() => {
            setShowAdd(true)
            setAddError(null)
          }}
          aria-label="Add override"
          className="h-9 rounded-[10px] border border-border px-3 text-[13px] text-text-secondary hover:text-text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
        >
          Add override
        </button>
      </div>

      {isLoading && (
        <p role="status" aria-label="Loading overrides" className="text-[14px] text-text-muted">
          Loading…
        </p>
      )}

      {!isLoading && (
        <div className="rounded-xl border border-border overflow-hidden">
          <table className="w-full text-[13px] font-mono">
            <thead className="bg-surface-sunken border-b border-border">
              <tr>
                <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em] font-sans">
                  Key
                </th>
                <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em] font-sans">
                  Value
                </th>
                <th className="text-left px-4 py-2 text-[11px] font-semibold text-text-muted uppercase tracking-[0.06em] font-sans">
                  Source
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {overriddenSettings.map(([key, item]) => (
                <tr key={key} className="hover:bg-surface-raised">
                  <td className="px-4 py-2 text-text-secondary">{key}</td>
                  <td className="px-4 py-2 text-text-primary">{JSON.stringify(item.value)}</td>
                  <td className="px-4 py-2">
                    <span className="inline-block rounded-full bg-surface-sunken px-2 py-0.5 text-[11px] font-sans text-text-muted">
                      {item.source}
                    </span>
                  </td>
                </tr>
              ))}
              {overriddenSettings.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-4 py-6 text-center font-sans text-[13px] text-text-muted">
                    No overrides set — all settings use global defaults.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showAdd && (
        <div className="rounded-xl border border-border bg-surface-raised p-4 space-y-3">
          <h3 className="text-[13px] font-semibold text-text-primary">Add override</h3>
          <div className="flex gap-2">
            <div className="flex-1">
              <label
                htmlFor="override-key"
                className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted"
              >
                Key
              </label>
              <input
                id="override-key"
                type="text"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder="scrfd_conf"
                className="h-9 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[13px] font-mono text-text-primary focus:border-brand-500 focus:outline-none"
              />
            </div>
            <div className="flex-1">
              <label
                htmlFor="override-value"
                className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted"
              >
                Value (JSON)
              </label>
              <input
                id="override-value"
                type="text"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="0.7"
                className="h-9 w-full rounded-[10px] border border-border bg-surface-base px-3 text-[13px] font-mono text-text-primary focus:border-brand-500 focus:outline-none"
              />
            </div>
          </div>
          {addError && (
            <p role="alert" className="text-[12px] text-error">
              {addError}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setShowAdd(false)
                setAddError(null)
              }}
              className="h-9 rounded-[10px] border border-border px-3 text-[13px] text-text-secondary hover:text-text-primary"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleAddOverride}
              disabled={saveMutation.isPending}
              className="h-9 rounded-[10px] bg-brand-500 px-3 text-[13px] font-medium text-white hover:bg-brand-700 disabled:opacity-40"
            >
              {saveMutation.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
