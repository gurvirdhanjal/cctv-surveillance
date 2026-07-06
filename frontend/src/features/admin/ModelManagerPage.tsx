import { Helmet } from 'react-helmet-async'
import { Cpu } from 'lucide-react'

/**
 * Model management is blocked on the P4 pre-work sub-task: implement
 * GET /api/models (model manifest endpoint) in the backend.
 * No models API endpoint exists yet; model files are managed via
 * models/manifest.json + vms-models CLI.
 * Track: plan 2026-06-24-vms-phase4-frontend.md — P4 sub-task.
 */
export function ModelManagerPage() {
  return (
    <>
      <Helmet title="Models — Admin" />
      <div className="p-6">
        <h1 className="mb-5 text-[22px] font-bold text-text-primary">Models</h1>
        <div
          role="status"
          aria-label="Models API unavailable"
          className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-surface-base py-20 text-center"
        >
          <Cpu className="mb-4 h-10 w-10 text-text-muted opacity-30" aria-hidden="true" />
          <p className="text-[15px] font-semibold text-text-secondary">Model manager coming soon</p>
          <p className="mt-1 max-w-sm text-[13px] text-text-muted">
            The /api/models backend endpoint is required. Models are currently managed via the{' '}
            <code>vms-models</code> CLI and models/manifest.json. Tracked: plan
            2026-06-24-vms-phase4-frontend.md — pre-work P4.
          </p>
        </div>
      </div>
    </>
  )
}
