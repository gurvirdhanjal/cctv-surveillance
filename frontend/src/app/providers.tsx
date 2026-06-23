import { type PropsWithChildren } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { IntlProvider } from 'react-intl'
import { HelmetProvider } from 'react-helmet-async'
import { ThemeProvider } from '@/components/ThemeProvider'
import { enMessages, DEFAULT_LOCALE } from '@/shared/i18n'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
})

export function Providers({ children }: PropsWithChildren) {
  return (
    <HelmetProvider>
      <QueryClientProvider client={queryClient}>
        <IntlProvider locale={DEFAULT_LOCALE} messages={enMessages}>
          <ThemeProvider>{children}</ThemeProvider>
        </IntlProvider>
      </QueryClientProvider>
    </HelmetProvider>
  )
}
