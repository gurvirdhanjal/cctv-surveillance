import { type PropsWithChildren } from 'react'
import { render, type RenderOptions } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { IntlProvider } from 'react-intl'
import { HelmetProvider } from 'react-helmet-async'
import { enMessages, DEFAULT_LOCALE } from '@/shared/i18n'

function AllProviders({ children }: PropsWithChildren) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  })
  return (
    <HelmetProvider>
      <QueryClientProvider client={client}>
        <IntlProvider locale={DEFAULT_LOCALE} messages={enMessages}>
          {children}
        </IntlProvider>
      </QueryClientProvider>
    </HelmetProvider>
  )
}

/** Render with all providers pre-wired. Prefer this over bare `render` in feature tests. */
export function renderWithProviders(ui: React.ReactElement, options?: Omit<RenderOptions, 'wrapper'>) {
  return render(ui, { wrapper: AllProviders, ...options })
}
