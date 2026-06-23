import { useEffect, type PropsWithChildren } from 'react'
import { useThemeStore } from '@/stores/themeStore'

export function ThemeProvider({ children }: PropsWithChildren) {
  const theme = useThemeStore((s) => s.theme)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  return <>{children}</>
}
