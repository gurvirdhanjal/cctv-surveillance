import { Helmet } from 'react-helmet-async'
import { ErrorBoundary } from './ErrorBoundary'

export function App() {
  return (
    <ErrorBoundary>
      <Helmet defaultTitle="VMS" titleTemplate="%s — VMS" />
      {/* Routes are added in 4B */}
      <div className="flex min-h-screen items-center justify-center bg-surface-base">
        <p className="text-[16px] text-text-secondary">VMS frontend loading&hellip;</p>
      </div>
    </ErrorBoundary>
  )
}
