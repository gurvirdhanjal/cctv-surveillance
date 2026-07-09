import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import * as Dialog from '@radix-ui/react-dialog'
import { Icon } from '@/shared/design-system/icons'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import { Button } from '@/shared/design-system/components/Button'

const clipSchema = z
  .object({
    camera_id: z.number({ required_error: 'Camera is required' }),
    start: z.string().min(1, 'Start time is required'),
    end: z.string().min(1, 'End time is required'),
    format: z.enum(['MP4', 'WebM']),
    label: z.string().optional(),
  })
  .refine((d) => new Date(d.end) > new Date(d.start), {
    message: 'End must be after start',
    path: ['end'],
  })

type ClipForm = z.infer<typeof clipSchema>

interface ClipExportDialogProps {
  open: boolean
  onClose: () => void
  cameraId?: number | null
  anchorMs?: number | null
}

export function ClipExportDialog({
  open,
  onClose,
  cameraId,
  anchorMs,
}: ClipExportDialogProps) {
  const anchorDate = anchorMs ? new Date(anchorMs) : new Date()
  const defaultStart = new Date(anchorDate.getTime() - 30_000).toISOString().slice(0, 16)
  const defaultEnd = new Date(anchorDate.getTime() + 30_000).toISOString().slice(0, 16)

  const { register, handleSubmit, formState: { errors }, reset } = useForm<ClipForm>({
    resolver: zodResolver(clipSchema),
    defaultValues: {
      camera_id: cameraId ?? undefined,
      start: defaultStart,
      end: defaultEnd,
      format: 'MP4',
    },
  })

  const { mutate, isPending, isSuccess, isError } = useMutation({
    mutationFn: (data: ClipForm) => api.post('/api/forensic/export', data),
    onSuccess: () => {
      setTimeout(() => { reset(); onClose() }, 2000)
    },
  })

  function onSubmit(data: ClipForm) {
    mutate(data)
  }

  return (
    <Dialog.Root open={open} onOpenChange={(o) => { if (!o) { reset(); onClose() } }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-[#1e293b] bg-[#111827] p-6 shadow-3 focus:outline-none"
          aria-label="Export clip"
        >
          <div className="flex items-center justify-between">
            <Dialog.Title className="text-[15px] font-semibold text-slate-100">
              Export Clip
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded-[10px] p-1.5 text-slate-400 hover:bg-[#1a2234] hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
                aria-label="Close"
              >
                <Icon.close className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          {isSuccess ? (
            <p className="mt-4 text-[13px] text-[#22c55e]">
              Export queued. Check the forensic search page for the download link.
            </p>
          ) : (
            <form onSubmit={handleSubmit(onSubmit)} className="mt-4 flex flex-col gap-4" noValidate>
              {/* Camera ID */}
              <div>
                <label htmlFor="clip-camera" className="mb-1 block text-[12px] text-slate-400">
                  Camera ID
                </label>
                <input
                  id="clip-camera"
                  type="number"
                  {...register('camera_id', { valueAsNumber: true })}
                  className="w-full rounded-[10px] border border-[#1e293b] bg-[#1a2234] px-3 py-2 text-[13px] text-slate-100 focus:outline-none focus:ring-1 focus:ring-[var(--focus-ring)]"
                  aria-describedby={errors.camera_id ? 'clip-camera-err' : undefined}
                />
                {errors.camera_id && (
                  <p id="clip-camera-err" className="mt-1 text-[12px] text-[#dc2626]">
                    {errors.camera_id.message}
                  </p>
                )}
              </div>

              {/* Start */}
              <div>
                <label htmlFor="clip-start" className="mb-1 block text-[12px] text-slate-400">
                  Start
                </label>
                <input
                  id="clip-start"
                  type="datetime-local"
                  {...register('start')}
                  className="w-full rounded-[10px] border border-[#1e293b] bg-[#1a2234] px-3 py-2 text-[13px] text-slate-100 focus:outline-none focus:ring-1 focus:ring-[var(--focus-ring)]"
                />
              </div>

              {/* End */}
              <div>
                <label htmlFor="clip-end" className="mb-1 block text-[12px] text-slate-400">
                  End
                </label>
                <input
                  id="clip-end"
                  type="datetime-local"
                  {...register('end')}
                  className="w-full rounded-[10px] border border-[#1e293b] bg-[#1a2234] px-3 py-2 text-[13px] text-slate-100 focus:outline-none focus:ring-1 focus:ring-[var(--focus-ring)]"
                  aria-describedby={errors.end ? 'clip-end-err' : undefined}
                />
                {errors.end && (
                  <p id="clip-end-err" className="mt-1 text-[12px] text-[#dc2626]">
                    {errors.end.message}
                  </p>
                )}
              </div>

              {/* Format */}
              <div>
                <label htmlFor="clip-format" className="mb-1 block text-[12px] text-slate-400">
                  Format
                </label>
                <select
                  id="clip-format"
                  {...register('format')}
                  className="w-full rounded-[10px] border border-[#1e293b] bg-[#1a2234] px-3 py-2 text-[13px] text-slate-100 focus:outline-none focus:ring-1 focus:ring-[var(--focus-ring)]"
                >
                  <option value="MP4">MP4</option>
                  <option value="WebM">WebM</option>
                </select>
              </div>

              {/* Label */}
              <div>
                <label htmlFor="clip-label" className="mb-1 block text-[12px] text-slate-400">
                  Label (optional)
                </label>
                <input
                  id="clip-label"
                  type="text"
                  {...register('label')}
                  className="w-full rounded-[10px] border border-[#1e293b] bg-[#1a2234] px-3 py-2 text-[13px] text-slate-100 focus:outline-none focus:ring-1 focus:ring-[var(--focus-ring)]"
                />
              </div>

              {isError && (
                <p className="text-[12px] text-[#dc2626]">
                  Export failed. Please try again.
                </p>
              )}

              <Button
                type="submit"
                size="sm"
                loading={isPending}
                disabled={isPending}
              >
                {isPending ? 'Exporting…' : 'Export'}
              </Button>
            </form>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
