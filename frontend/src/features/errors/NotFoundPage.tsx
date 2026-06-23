import { Link } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'

export function NotFoundPage() {
  return (
    <>
      <Helmet title="Not Found" />
      <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-surface-sunken px-4 text-center">
        <p className="font-mono text-[64px] font-bold leading-none text-text-muted">404</p>
        <div className="flex flex-col gap-1">
          <h1 className="text-[20px] font-semibold text-text-primary">Page not found</h1>
          <p className="text-[14px] text-text-secondary">
            The page you requested does not exist.
          </p>
        </div>
        <Link
          to="/"
          className="rounded-md bg-brand-500 px-4 py-2 text-[14px] font-medium text-white hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
        >
          Go to dashboard
        </Link>
      </div>
    </>
  )
}
