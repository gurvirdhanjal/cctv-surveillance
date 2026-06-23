import { Helmet } from 'react-helmet-async'

/** Stub — implemented in Phase 4C */
export function GuardView() {
  return (
    <>
      <Helmet title="Guard View" />
      <div className="flex min-h-screen items-center justify-center bg-surface-base">
        <p className="text-[16px] text-text-secondary">Guard view — coming in 4C</p>
      </div>
    </>
  )
}
