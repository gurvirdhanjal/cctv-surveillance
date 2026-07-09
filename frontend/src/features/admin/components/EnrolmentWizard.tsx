import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import { Button } from '@/shared/design-system/components/Button'

const step1Schema = z.object({
  name: z.string().min(2, 'Name must be at least 2 characters').max(200),
  employee_id: z
    .string()
    .regex(/^EMP-\d{3,6}$/, 'Format: EMP-XXXXXX (3–6 digits, e.g. EMP-001234)'),
})

type Step1Data = z.infer<typeof step1Schema>

const STEPS = ['Personal Info', 'Capture', 'Quality Check', 'Confirm'] as const
type StepIndex = 0 | 1 | 2 | 3

interface Props {
  onDone: (personId: number) => void
  onCancel: () => void
}

export function EnrolmentWizard({ onDone, onCancel }: Props) {
  const [step, setStep] = useState<StepIndex>(0)
  const [step1Data, setStep1Data] = useState<Step1Data | null>(null)
  const [confirmCancel, setConfirmCancel] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isDirty },
  } = useForm<Step1Data>({ resolver: zodResolver(step1Schema) })

  const enrolMutation = useMutation({
    mutationFn: async (data: Step1Data) => {
      const person = await api.post<{ person_id: number }>('/api/persons', {
        name: data.name,
        employee_id: data.employee_id,
      })
      return person.person_id
    },
    onSuccess: (personId) => onDone(personId),
  })

  function handleStep1Submit(data: Step1Data) {
    setStep1Data(data)
    setStep(1)
  }

  function handleNext() {
    setStep((s) => Math.min(s + 1, 3) as StepIndex)
  }

  function handleBack() {
    setStep((s) => Math.max(s - 1, 0) as StepIndex)
  }

  function handleCancelClick() {
    if (isDirty || step1Data) {
      setConfirmCancel(true)
    } else {
      onCancel()
    }
  }

  function handleFinalSave() {
    if (step1Data) enrolMutation.mutate(step1Data)
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Enrol new person"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div className="bg-surface-base rounded-lg shadow-lg w-full max-w-lg p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-[18px] font-semibold text-text-primary">Enrol New Person</h2>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Cancel enrolment"
            onClick={handleCancelClick}
            className="text-[20px] leading-none text-text-muted hover:text-text-primary"
          >
            ×
          </Button>
        </div>

        {/* Step indicator */}
        <ol aria-label="Wizard steps" className="flex gap-2 mb-6">
          {STEPS.map((label, i) => (
            <li
              key={label}
              className={`flex-1 text-center text-[12px] py-1 rounded ${
                i === step
                  ? 'bg-[var(--interactive-primary)] text-text-inverse font-medium'
                  : i < step
                    ? 'bg-brand-100 text-brand-700'
                    : 'bg-surface-sunken text-text-muted'
              }`}
              aria-current={i === step ? 'step' : undefined}
            >
              {label}
            </li>
          ))}
        </ol>

        {/* Step content */}
        {step === 0 && (
          <form
            aria-label="Personal info form"
            onSubmit={handleSubmit(handleStep1Submit)}
            className="space-y-4"
          >
            <div>
              <label
                htmlFor="enrol-name"
                className="block text-[13px] font-medium text-text-secondary mb-1"
              >
                Full name
              </label>
              <input
                id="enrol-name"
                {...register('name')}
                className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)]"
                placeholder="Ranjeet Kumar"
              />
              {errors.name && (
                <p role="alert" className="mt-1 text-[12px] text-error">
                  {errors.name.message}
                </p>
              )}
            </div>
            <div>
              <label
                htmlFor="enrol-emp-id"
                className="block text-[13px] font-medium text-text-secondary mb-1"
              >
                Employee ID
              </label>
              <input
                id="enrol-emp-id"
                {...register('employee_id')}
                className="w-full border border-border rounded px-3 py-2 text-[14px] bg-surface-base text-text-primary font-mono focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)]"
                placeholder="EMP-001234"
              />
              {errors.employee_id && (
                <p role="alert" className="mt-1 text-[12px] text-error">
                  {errors.employee_id.message}
                </p>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="secondary"
                onClick={handleCancelClick}
              >
                Cancel
              </Button>
              <Button type="submit">
                Next
              </Button>
            </div>
          </form>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <p className="text-[14px] text-text-secondary">
              Position the person in front of the camera and capture their face. The system requires
              at least one clear frontal face image.
            </p>
            <div
              className="h-40 bg-surface-sunken rounded flex items-center justify-center border border-border"
              aria-label="Camera capture area"
            >
              <p className="text-[13px] text-text-muted">Camera capture (simulated)</p>
            </div>
            <div className="flex justify-between pt-2">
              <Button
                type="button"
                variant="secondary"
                onClick={handleBack}
              >
                Back
              </Button>
              <Button type="button" onClick={handleNext}>
                Next
              </Button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <p className="text-[14px] text-text-secondary">
              Checking image quality — face detection, sharpness, and lighting.
            </p>
            <div className="bg-success/10 border border-success/20 rounded p-3 text-[13px] text-success">
              Quality check passed. Ready to save.
            </div>
            <div className="flex justify-between pt-2">
              <Button
                type="button"
                variant="secondary"
                onClick={handleBack}
              >
                Back
              </Button>
              <Button type="button" onClick={handleNext}>
                Next
              </Button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <dl className="space-y-2 text-[14px]">
              <div className="flex gap-4">
                <dt className="w-28 text-text-muted">Name</dt>
                <dd className="text-text-primary font-medium">{step1Data?.name ?? '—'}</dd>
              </div>
              <div className="flex gap-4">
                <dt className="w-28 text-text-muted">Employee ID</dt>
                <dd className="text-text-primary font-mono">{step1Data?.employee_id ?? '—'}</dd>
              </div>
            </dl>
            {enrolMutation.isError && (
              <p role="alert" className="text-[13px] text-error">
                Save failed. Please try again.
              </p>
            )}
            <div className="flex justify-between pt-2">
              <Button
                type="button"
                variant="secondary"
                onClick={handleBack}
              >
                Back
              </Button>
              <Button
                type="button"
                onClick={handleFinalSave}
                disabled={enrolMutation.isPending}
                loading={enrolMutation.isPending}
              >
                Save
              </Button>
            </div>
          </div>
        )}
      </div>

      {confirmCancel && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Confirm cancel"
          className="fixed inset-0 z-60 flex items-center justify-center bg-black/50"
        >
          <div className="bg-surface-base rounded p-6 max-w-sm w-full shadow-xl">
            <p className="text-[15px] font-medium text-text-primary mb-2">Discard changes?</p>
            <p className="text-[13px] text-text-secondary mb-4">
              Partial enrolment data will be lost.
            </p>
            <div className="flex gap-2 justify-end">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setConfirmCancel(false)}
              >
                Keep editing
              </Button>
              <Button
                type="button"
                variant="destructive"
                onClick={onCancel}
              >
                Discard
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
