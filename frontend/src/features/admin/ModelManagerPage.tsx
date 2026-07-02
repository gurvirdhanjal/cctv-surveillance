import { Helmet } from 'react-helmet-async'

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
      <div className="p-6 max-w-2xl">
        <h1 className="text-[22px] font-semibold text-text-primary mb-4">Models</h1>
        <div
          role="status"
          aria-label="Models API unavailable"
          className="bg-surface-elevated border border-border-subtle rounded p-6 text-center"
        >
          <p className="text-[15px] font-medium text-text-primary mb-2">
            Model management is not yet available
          </p>
          <p className="text-[13px] text-text-secondary mb-3">
            The Models API (GET /api/models) needs to be implemented in the backend before this
            page can be used. Models are currently managed via the{' '}
            <code className="font-mono bg-surface-sunken px-1 rounded">vms-models</code> CLI and
            the{' '}
            <code className="font-mono bg-surface-sunken px-1 rounded">models/manifest.json</code>{' '}
            file.
          </p>
          <p className="text-[12px] text-text-tertiary font-mono">
            Tracked: plan 2026-06-24-vms-phase4-frontend.md — pre-work P4
          </p>
        </div>
      </div>
    </>
  )
}
