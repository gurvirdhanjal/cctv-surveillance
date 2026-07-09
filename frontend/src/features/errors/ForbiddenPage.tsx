import { Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'

export function ForbiddenPage() {
  return (
    <>
      <Helmet title="Access Denied" />
      <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-surface-sunken px-4 text-center">
        <p className="font-mono text-[64px] font-bold leading-none text-text-muted">403</p>
        <div className="flex flex-col gap-1">
          <h1 className="text-[20px] font-semibold text-text-primary">Access denied</h1>
          <p className="text-[14px] text-text-secondary">
            You do not have permission to view this page.
          </p>
        </div>
        <Link
          to="/"
          className="inline-flex h-10 items-center gap-2 rounded-md bg-[var(--interactive-primary)] px-4 text-[14px] font-medium text-text-inverse shadow-1 hover:bg-[var(--interactive-hover)] transition-colors duration-quick focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
        >
          Go to dashboard
        </Link>
      </div>
    </>
  )
}
