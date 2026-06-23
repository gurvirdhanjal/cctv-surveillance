import { BrowserRouter } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { ErrorBoundary } from './ErrorBoundary'
import { AuthRedirect } from './AuthRedirect'
import { AppRoutes } from './routes'

export function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Helmet defaultTitle="VMS" titleTemplate="%s — VMS" />
        <AuthRedirect />
        <AppRoutes />
      </BrowserRouter>
    </ErrorBoundary>
  )
}
