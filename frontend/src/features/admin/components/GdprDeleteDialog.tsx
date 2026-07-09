import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { request } from '@/shared/api/client'
import { Button } from '@/shared/design-system/components/Button'

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
      request(`/api/persons/${personId}`, {
        method: 'DELETE',
        body: { confirmation_name: confirmationName, reason },
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
              className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)]"
            />
            <p id="gdpr-name-hint" className="mt-1 text-[12px] text-text-muted">
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
              className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary resize-none focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)]"
              placeholder="GDPR erasure request received on…"
            />
            <p className="mt-1 text-[12px] text-text-muted">
              {reason.trim().length}/10 minimum characters
            </p>
          </div>

          {deleteMutation.isError && (
            <p role="alert" className="text-[13px] text-error">
              Deletion failed. Please try again.
            </p>
          )}

          <div className="flex gap-2 justify-end pt-2">
            <Button
              type="button"
              variant="secondary"
              onClick={onCancel}
              disabled={deleteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => deleteMutation.mutate()}
              disabled={!canDelete || deleteMutation.isPending}
              aria-disabled={!canDelete || deleteMutation.isPending}
              loading={deleteMutation.isPending}
            >
              Delete Person
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
