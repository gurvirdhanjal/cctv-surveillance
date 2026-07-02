import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/shared/api/client'

interface Props {
  personId: number
  personName: string
  onConfirmed: () => void
  onCancel: () => void
}

export function GdprDeleteDialog({ personId, personName, onConfirmed, onCancel }: Props) {
  const [confirmationName, setConfirmationName] = useState('')
  const [reason, setReason] = useState('')

  const nameMatches = confirmationName === personName
  const reasonValid = reason.trim().length >= 10
  const canDelete = nameMatches && reasonValid

  const deleteMutation = useMutation({
    mutationFn: () =>
      api.delete(`/api/persons/${personId}`, {
        body: JSON.stringify({ confirmation_name: confirmationName, reason }),
      }),
    onSuccess: onConfirmed,
  })

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="GDPR person delete"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
    >
      <div className="bg-surface-base rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 className="text-[17px] font-semibold text-text-primary mb-1">Delete Person Record</h2>
        <p className="text-[13px] text-text-secondary mb-4">
          This permanently removes all biometric data, embeddings, and thumbnails for{' '}
          <strong>{personName}</strong>. This action cannot be undone.
        </p>

        <div className="space-y-4">
          <div>
            <label
              htmlFor="gdpr-confirm-name"
              className="block text-[13px] font-medium text-text-secondary mb-1"
            >
              Type the person's full name to confirm
            </label>
            <input
              id="gdpr-confirm-name"
              type="text"
              value={confirmationName}
              onChange={(e) => setConfirmationName(e.target.value)}
              placeholder={personName}
              aria-describedby="gdpr-name-hint"
              className="w-full border border-border-subtle rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary focus:outline-none focus:ring-2 focus:ring-red-500"
            />
            <p id="gdpr-name-hint" className="mt-1 text-[12px] text-text-tertiary">
              Must match exactly: {personName}
            </p>
          </div>

          <div>
            <label
              htmlFor="gdpr-reason"
              className="block text-[13px] font-medium text-text-secondary mb-1"
            >
              Reason for deletion (min 10 characters)
            </label>
            <textarea
              id="gdpr-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              className="w-full border border-border-subtle rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary resize-none focus:outline-none focus:ring-2 focus:ring-red-500"
              placeholder="GDPR erasure request received on…"
            />
            <p className="mt-1 text-[12px] text-text-tertiary">
              {reason.trim().length}/10 minimum characters
            </p>
          </div>

          {deleteMutation.isError && (
            <p role="alert" className="text-[13px] text-red-600">
              Deletion failed. Please try again.
            </p>
          )}

          <div className="flex gap-2 justify-end pt-2">
            <button
              type="button"
              onClick={onCancel}
              disabled={deleteMutation.isPending}
              className="px-4 py-2 text-[14px] rounded border border-border-subtle text-text-secondary hover:text-text-primary disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => deleteMutation.mutate()}
              disabled={!canDelete || deleteMutation.isPending}
              aria-disabled={!canDelete || deleteMutation.isPending}
              className="px-4 py-2 text-[14px] rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {deleteMutation.isPending ? 'Deleting…' : 'Delete Person'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
