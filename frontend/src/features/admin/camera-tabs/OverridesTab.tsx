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
          className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded p-3 text-[13px] text-amber-900"
        >
          <span aria-hidden="true">⚠</span>
          <span>
            Shutter-type overrides are set. Verify the override matches the physical camera sensor
            before saving.
          </span>
        </div>
      )}

      <div className="flex items-center justify-between">
        <h2 className="text-[15px] font-medium text-text-primary">Per-camera overrides</h2>
        <button
          type="button"
          onClick={() => {
            setShowAdd(true)
            setAddError(null)
          }}
          className="px-3 py-1.5 text-[13px] rounded border border-border text-text-secondary hover:text-text-primary"
        >
          Add override
        </button>
      </div>

      {isLoading && (
        <p role="status" aria-label="Loading overrides">
          Loading…
        </p>
      )}

      {!isLoading && (
        <div className="rounded border border-border overflow-hidden">
          <table className="w-full text-[13px] font-mono">
            <thead className="bg-surface-sunken border-b border-border">
              <tr>
                <th className="text-left px-4 py-2 text-text-muted font-medium">Key</th>
                <th className="text-left px-4 py-2 text-text-muted font-medium">Value</th>
                <th className="text-left px-4 py-2 text-text-muted font-medium">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {overriddenSettings.map(([key, item]) => (
                <tr key={key} className="hover:bg-surface-raised">
                  <td className="px-4 py-2 text-text-secondary">{key}</td>
                  <td className="px-4 py-2 text-text-primary">{JSON.stringify(item.value)}</td>
                  <td className="px-4 py-2 text-text-muted">{item.source}</td>
                </tr>
              ))}
              {overriddenSettings.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-4 py-4 text-center text-text-muted">
                    No overrides set — all settings use global defaults.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showAdd && (
        <div className="border border-border rounded p-4 space-y-3 bg-surface-raised">
          <h3 className="text-[14px] font-medium text-text-primary">Add override</h3>
          <div className="flex gap-2">
            <div className="flex-1">
              <label
                htmlFor="override-key"
                className="block text-[12px] text-text-muted mb-1"
              >
                Key
              </label>
              <input
                id="override-key"
                type="text"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder="scrfd_conf"
                className="w-full border border-border rounded px-2 py-1.5 text-[13px] font-mono bg-surface-base focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div className="flex-1">
              <label
                htmlFor="override-value"
                className="block text-[12px] text-text-muted mb-1"
              >
                Value (JSON)
              </label>
              <input
                id="override-value"
                type="text"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="0.7"
                className="w-full border border-border rounded px-2 py-1.5 text-[13px] font-mono bg-surface-base focus:outline-none focus:ring-2 focus:ring-brand-500"
              />
            </div>
          </div>
          {addError && (
            <p role="alert" className="text-[12px] text-red-600">
              {addError}
            </p>
          )}
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={() => {
                setShowAdd(false)
                setAddError(null)
              }}
              className="px-3 py-1.5 text-[13px] rounded border border-border text-text-secondary"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleAddOverride}
              disabled={saveMutation.isPending}
              className="px-3 py-1.5 text-[13px] rounded bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
