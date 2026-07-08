import { BrowserRouter } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { ErrorBoundary } from './ErrorBoundary'
import { AuthRedirect } from './AuthRedirect'
import { AppRoutes } from './routes'
import { CommandPalette } from '@/shared/command/CommandPalette'

export function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Helmet defaultTitle="VMS" titleTemplate="%s — VMS" />
        <AuthRedirect />
        <AppRoutes />
        <CommandPalette />
      </BrowserRouter>
    </ErrorBoundary>
  )
}
